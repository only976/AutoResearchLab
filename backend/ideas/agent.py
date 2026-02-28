import os, json, re, hashlib, requests, io, uuid
import xml.etree.ElementTree as ET
from typing import Dict, List,Any
import pypdf
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer



from google.adk.agents import Agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from google.adk.models.lite_llm import LiteLlm
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY
from backend.utils.logger import setup_logger
from backend.ideas.templates import (
    RESEARCH_TOPIC_SCHEMA,
    ADVANCED_REPORT_SCHEMA,
    get_advanced_instruction,
    get_template_descriptions # 保持兼容
)

class IdeaAgent:
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        if LLM_API_BASE:
            self.model = LiteLlm(
                model=LLM_MODEL,
                api_base=LLM_API_BASE,
                api_key=LLM_API_KEY
            )
        else:
            self.model = LLM_MODEL
        self.tools = [self.search_literature]

    def search_literature(self, query: str, limit: int = 5) -> str:
        words = re.findall(r"\w+", query)
        if not words:
            return "No query provided."
        url = f"http://export.arxiv.org/api/query?search_query=all:{'+'.join(words[:5])}&max_results={limit}"
        try:
            resp = requests.get(url, timeout=20)
            root = ET.fromstring(resp.content)
            results = []
            for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                title = entry.find("{http://www.w3.org/2005/Atom}title").text.strip().replace("\n", " ")
                link_node = entry.find("{http://www.w3.org/2005/Atom}link[@rel='alternate']")
                link_url = link_node.attrib["href"] if link_node is not None else ""
                results.append(f"{title} | {link_url}")
            return "\n".join(results) if results else "No results found."
        except Exception as e:
            return f"Error: {e}"

    def refine_topic(self, raw_scope: str) -> str:
        instruction = f"""
You are a Research Topic Refiner.
Determine if the input is broad or specific.
If broad, propose 3 focused research topics.
If specific, return 1 refined topic.
Output JSON only with keys: is_broad (bool), analysis (str), topics (list).
Each topic must follow this schema: {RESEARCH_TOPIC_SCHEMA}.
"""
        agent = Agent(
            model=self._get_model_for_agent(),
            name="idea_refiner",
            instruction=instruction,
            tools=[]
        )
        runner = Runner(
            agent=agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )
        try:
            events = runner.run(
                user_id="user",
                session_id=str(uuid.uuid4()),
                new_message=Content(role="user", parts=[Part(text=raw_scope)])
            )
            final_text = self._collect_text(events)
            return self._clean_json_text(final_text)
        except Exception as e:
            self.logger.error(f"Topic refinement failed: {e}", exc_info=True)
            return json.dumps({"is_broad": False, "analysis": str(e), "topics": []}, ensure_ascii=False)

    def generate_ideas(self, scope: str, vram: int = 24, level: str = "master", lang: str = "zh") -> str:
        # --- 修改开始 ---
        # 调用你新写的指令工厂
        instruction = get_advanced_instruction(scope, vram, level, lang)
        # --- 修改结束 ---

        agent = Agent(
            model=self._get_model_for_agent(),
            name="idea_generator",
            instruction=instruction,  # 使用新指令
            tools=self.tools
        )
        # 下面的 runner.run 逻辑完全不动
        runner = Runner(agent=agent, app_name="auto_research", session_service=InMemorySessionService(),
                        auto_create_session=True)
        try:
            events = runner.run(
                user_id="user",
                session_id=str(uuid.uuid4()),
                new_message=Content(role="user", parts=[Part(text=scope)])
            )
            final_text = self._collect_text(events)
            return self._clean_json_text(final_text)
        except Exception as e:
            self.logger.error(f"Idea generation failed: {e}", exc_info=True)
            return json.dumps({"reasoning": {}, "ideas": [], "error": str(e)}, ensure_ascii=False)

    def _collect_text(self, events) -> str:
        final_text = ""
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final_text += part.text
        return final_text.strip()

    def _clean_json_text(self, text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    def _get_model_for_agent(self):
        model = self.model
        if isinstance(model, str):
            return model
        if type(model).__module__.startswith("google.adk."):
            return model
        return str(model)

class ResearchIdeaEngine:
    def __init__(self, model_config: dict, db_path: str):
        if model_config.get("api_base"):
            self.model = LiteLlm(model=model_config["model_name"], api_base=model_config["api_base"],
                                 api_key=model_config["api_key"])
        else:
            self.model = model_config["model_name"]

        cloud_url = os.getenv("QDRANT_URL")
        cloud_key = os.getenv("QDRANT_API_KEY")

        if cloud_url and cloud_key:
            print(f"🌐 正在连接 Qdrant Cloud...")
            self.qclient = QdrantClient(url=cloud_url, api_key=cloud_key, timeout=60)
        else:
            print(f"🏠 使用本地数据库模式: {db_path}")
            self.qclient = QdrantClient(path=os.path.abspath(db_path))

        self.collection_name = "academic_chunks"
        self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "pdf_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.current_chunks = []

        if not self.qclient.collection_exists(self.collection_name):
            self.qclient.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )

        self.agent = Agent(model=self.model, name="research_proposer",
                           tools=[self.search_and_index_tool, self.query_knowledge_base])

    def search_and_index_tool(self, topic: str, limit: int = 30) -> str:
        words = re.findall(r"\w+", topic)
        url = f"http://export.arxiv.org/api/query?search_query=all:{'+'.join(words[:5])}&max_results={limit}"
        success_count = 0
        try:
            resp = requests.get(url, timeout=20)
            root = ET.fromstring(resp.content)
            for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                title = entry.find("{http://www.w3.org/2005/Atom}title").text.strip().replace("\n", " ")
                link_node = entry.find("{http://www.w3.org/2005/Atom}link[@rel='alternate']")
                if link_node is None: continue
                link_url = link_node.attrib['href']

                pdf_chunks = self._download_and_extract_pdf(link_url)
                if not pdf_chunks: continue

                points = [PointStruct(
                    id=hashlib.md5(f"{title}_{idx}".encode()).hexdigest(),
                    vector=self.encoder.encode(c["content"]).tolist(),
                    payload={"title": title, "text": c["content"], "page": c["page"], "url": link_url}
                ) for idx, c in enumerate(pdf_chunks)]

                if points:
                    self.qclient.upsert(collection_name=self.collection_name, points=points)
                    success_count += 1
            print(f"✅ 成功同步了 {success_count} 篇论文到云端。")
            return f"Success: Indexed {success_count} papers."
        except Exception as e:
            return f"Error: {e}"

    def query_knowledge_base(self, query: str) -> str:
        """【调试】增加打印，确认 Agent 是否在检索"""
        print(f"🔍 Agent 正在检索知识库: {query}")
        vector = self.encoder.encode(query).tolist()
        result = self.qclient.query_points(collection_name=self.collection_name, query=vector, limit=90)
        self.current_chunks = [p.payload for p in result.points]
        print(f"💡 检索到 {len(self.current_chunks)} 条相关片段。")
        return "\n\n".join([f"[Source ID: {i}] (Title: {p.payload['title']})\n{p.payload['text']}" for i, p in
                            enumerate(result.points)])

    def run_agent_workflow(self, input_json: Dict[str, Any]):
        """
        集成：适配前端输入格式的 RAG 工作流。
        input_json 包含: broad_topic, depth_level, vram_gb, language 等。
        """
        from backend.ideas.templates import get_advanced_instruction

        # 1. 从输入 JSON 中提取参数（设置默认值以防前端漏传）
        topic = input_json.get("broad_topic", "Unknown Topic")
        vram = input_json.get("vram_gb", 24)
        level = input_json.get("depth_level", "master")
        lang = input_json.get("language", "zh")

        # 2. 动态生成系统指令
        self.agent.instruction = get_advanced_instruction(topic, vram, level, lang)

        runner = Runner(
            agent=self.agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )

        # 3. 构造任务提示词
        prompt = f"请先通过 query_knowledge_base 检索关于 '{topic}' 的文献，然后根据检索到的 Source ID 给出 JSON 报告。"

        # 4. 执行 Agent 逻辑
        events = runner.run(
            user_id="admin",
            session_id=str(uuid.uuid4()),
            new_message=Content(role="user", parts=[Part(text=prompt)])
        )

        # 5. 文本收集与工具过滤
        final_text = ""
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        if any(x in part.text for x in ["<|tool", "<function", "调用工具"]):
                            continue
                        final_text += part.text

        # 6. JSON 提取与召回率计算
        match = re.search(r'(\{.*\})', final_text, re.DOTALL)
        if match:
            json_str = match.group(1)
            try:
                raw_res = json.loads(json_str)
            except json.JSONDecodeError:
                json_str_fixed = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', json_str)
                raw_res = json.loads(json_str_fixed)

            # 7. 计算召回（Recall Metrics）
            cited_ids = raw_res.get("cited_source_ids", [])
            cited_map = {}
            for i in cited_ids:
                try:
                    idx = int(i)
                    if idx < len(self.current_chunks):
                        chunk = self.current_chunks[idx]
                        cited_map[chunk['title']] = chunk.get('url', 'N/A')
                except:
                    continue

            # 8. 注入召回指标和原始输入元数据
            raw_res["recall_metrics"] = {
                "recall_score": round(len(cited_map) / 10, 2) if self.current_chunks else 0,
                "cited_papers": [f"{t} ({u})" for t, u in cited_map.items()],
                "total_papers": list(set([f"{p['title']} ({p.get('url', 'N/A')})" for p in self.current_chunks]))[:10]
            }
            # 保留输入参数快照，方便前端展示
            raw_res["config_snapshot"] = {
                "vram": f"{vram}GB",
                "level": level,
                "topic": topic
            }
            return raw_res

        return {"error": "No JSON found", "raw": final_text}

    def _download_and_extract_pdf(self, pdf_url: str) -> List[Dict]:
        url_hash = hashlib.md5(pdf_url.encode()).hexdigest()
        cache_path = os.path.join(self.cache_dir, f"{url_hash}.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f: return json.load(f)
        try:
            pdf_link = pdf_url.replace("/abs/", "/pdf/") + ".pdf"
            response = requests.get(pdf_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
            if not response.content.startswith(b'%PDF'): return []
            reader = pypdf.PdfReader(io.BytesIO(response.content))
            chunks = [{"content": p.extract_text().replace("\n", " ")[:1000], "page": i + 1} for i, p in
                      enumerate(reader.pages[:10]) if p.extract_text()] # 只取前 10 页提高速度
            if chunks:
                with open(cache_path, "w", encoding="utf-8") as f: json.dump(chunks, f, ensure_ascii=False)
            return chunks
        except: return []
