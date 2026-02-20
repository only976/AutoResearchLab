import os, json, re, hashlib, requests, io, uuid
import xml.etree.ElementTree as ET
from typing import Dict, List
import pypdf
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from google.adk.agents import Agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from google.adk.models.lite_llm import LiteLlm

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

    def run_agent_workflow(self, topic: str, system_instruction: str):
        self.agent.instruction = system_instruction
        runner = Runner(agent=self.agent, app_name="auto_research", session_service=InMemorySessionService(),
                        auto_create_session=True)
        final_text = ""
        # 强制增加一个 user 信息，提醒它必须先 query
        prompt = f"请先通过 query_knowledge_base 检索关于 '{topic}' 的文献，然后根据检索到的 Source ID 给出 JSON 报告。"
        events = runner.run(user_id="admin", session_id=str(uuid.uuid4()),
                            new_message=Content(role="user", parts=[Part(text=prompt)]))

        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        if any(x in part.text for x in ["<|tool", "<function", "调用工具"]): continue
                        final_text += part.text

        match = re.search(r'(\{.*\})', final_text, re.DOTALL)
        if match:
            json_str = match.group(1)
            try:
                raw_res = json.loads(json_str)
            except json.JSONDecodeError:
                json_str_fixed = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', json_str)
                raw_res = json.loads(json_str_fixed)

            # 核心：计算召回
            cited_ids = raw_res.get("cited_source_ids", [])
            cited_map = {}
            for i in cited_ids:
                try:
                    idx = int(i)
                    if idx < len(self.current_chunks):
                        title = self.current_chunks[idx]['title']
                        cited_map[title] = self.current_chunks[idx].get('url', 'N/A')
                except: continue

            raw_res["recall_metrics"] = {
                "recall_score": round(len(cited_map) / 10, 2) if len(self.current_chunks) > 0 else 0, # 以 10 篇为基准参考
                "cited_papers": [f"{t} ({u})" for t, u in cited_map.items()],
                "total_papers": list(set([f"{p['title']} ({p.get('url', 'N/A')})" for p in self.current_chunks]))[:10]
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
                      enumerate(reader.pages[:3]) if p.extract_text()] # 只取前 3 页提高速度
            if chunks:
                with open(cache_path, "w", encoding="utf-8") as f: json.dump(chunks, f, ensure_ascii=False)
            return chunks
        except: return []