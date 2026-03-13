"""
Idea Agent PDF RAG 引擎 - 将筛选后的论文 PDF 正文向量化并支持语义检索。
参考 ARL ResearchIdeaEngine，支持 Qdrant 本地/云端。
"""

import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

# 延迟导入，依赖可选
_QdrantClient = None
_SentenceTransformer = None
_PdfReader = None


def _ensure_imports() -> bool:
    """延迟加载 RAG 依赖，失败时返回 False。"""
    global _QdrantClient, _SentenceTransformer, _PdfReader
    if _QdrantClient is not None:
        return True
    try:
        from qdrant_client import QdrantClient as _QC
        from qdrant_client.models import Distance, PointStruct, VectorParams
        from pypdf import PdfReader as _PR
        from sentence_transformers import SentenceTransformer as _ST

        globals()["_QdrantClient"] = _QC
        globals()["_SentenceTransformer"] = _ST
        globals()["_PdfReader"] = _PR
        return True
    except ImportError as e:
        logger.debug("RAG dependencies not available: %s", e)
        return False


class IdeaRAGEngine:
    """PDF 向量检索引擎，用于 Idea Agent 精细 refine。"""

    COLLECTION_NAME = "academic_chunks"
    VECTOR_SIZE = 384
    MAX_PAGES = 10
    CHUNK_CHARS = 1000

    def __init__(self, qdrant_path: Optional[Path] = None):
        """
        初始化 RAG 引擎。
        qdrant_path: 本地 Qdrant 存储路径，默认 db/qdrant/
        若设置 QDRANT_URL + QDRANT_API_KEY 环境变量，则使用云端。
        """
        self._client = None
        self._encoder = None
        self._initialized = False
        self._qdrant_path = qdrant_path
        self._cache_dir: Optional[Path] = None

    def _init(self) -> bool:
        """延迟初始化，依赖可用时返回 True。"""
        if self._initialized:
            return self._client is not None
        if not _ensure_imports():
            return False
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            from sentence_transformers import SentenceTransformer

            cloud_url = os.getenv("QDRANT_URL")
            cloud_key = os.getenv("QDRANT_API_KEY")
            if cloud_url and cloud_key:
                self._client = QdrantClient(url=cloud_url, api_key=cloud_key, timeout=60)
            else:
                path = self._qdrant_path or (Path(__file__).resolve().parent.parent / "db" / "qdrant")
                path.mkdir(parents=True, exist_ok=True)
                self._client = QdrantClient(path=str(path), timeout=60)

            if not self._client.collection_exists(self.COLLECTION_NAME):
                self._client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(size=self.VECTOR_SIZE, distance=Distance.COSINE),
                )

            self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
            cache_base = Path(__file__).resolve().parent.parent / "db" / "pdf_cache"
            self._cache_dir = cache_base
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._initialized = True
            return True
        except Exception as e:
            logger.warning("IdeaRAGEngine init failed: %s", e)
            return False

    def _get_pdf_chunks(self, pdf_url: str) -> List[Dict]:
        """下载 PDF 并提取前 N 页文本，带缓存。"""
        import io

        from pypdf import PdfReader

        url_hash = hashlib.md5(pdf_url.encode()).hexdigest()
        cache_path = self._cache_dir / f"{url_hash}.json"
        if cache_path.exists():
            import json

            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        try:
            pdf_link = pdf_url.replace("/abs/", "/pdf/") + ".pdf"
            import httpx

            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(pdf_link, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                content = resp.content
            if not content.startswith(b"%PDF"):
                return []
            reader = PdfReader(io.BytesIO(content))
            chunks = []
            for i, page in enumerate(reader.pages[: self.MAX_PAGES]):
                text = page.extract_text()
                if text:
                    chunks.append({"content": text.replace("\n", " ")[: self.CHUNK_CHARS], "page": i + 1})
            if chunks:
                import json

                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(chunks, f, ensure_ascii=False)
            return chunks
        except Exception as e:
            logger.debug("PDF fetch failed for %s: %s", pdf_url[:50], e)
            return []

    async def index_papers(self, papers: List[dict]) -> str:
        """
        将论文列表索引到 Qdrant。
        papers: [{title, url, ...}, ...]，需含 url 字段。
        每次调用前清空集合，确保仅当前 session 的论文。
        返回 "Indexed N papers" 或错误信息。
        """
        if not self._init():
            return "Error: RAG dependencies not available (qdrant-client, sentence-transformers, pypdf)"
        try:
            logger.info("Idea RAG Engine: indexing papers=%d", len(papers or []))
        except Exception:
            pass
        from qdrant_client.models import Distance, PointStruct, VectorParams

        all_points = []
        for paper in papers or []:
            url = paper.get("url") or paper.get("link") or ""
            title = paper.get("title") or "Untitled"
            if not url or "/abs/" not in url:
                continue
            chunks = self._get_pdf_chunks(url)
            if not chunks:
                continue
            for idx, c in enumerate(chunks):
                content = c.get("content", "")
                if not content.strip():
                    continue
                vector = self._encoder.encode(content).tolist()
                point_id = hashlib.md5(f"{title}_{idx}_{url}".encode()).hexdigest()
                all_points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={"title": title, "text": content, "page": c.get("page", 0), "url": url},
                    )
                )
        if not all_points:
            logger.info("Idea RAG Engine: no chunks extracted from PDFs")
            return "No papers indexed (no PDF content extracted)."
        try:
            if self._client.collection_exists(self.COLLECTION_NAME):
                self._client.delete_collection(self.COLLECTION_NAME)
        except Exception:
            pass
        if not self._client.collection_exists(self.COLLECTION_NAME):
            self._client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(size=self.VECTOR_SIZE, distance=Distance.COSINE),
            )
        self._client.upsert(collection_name=self.COLLECTION_NAME, points=all_points)
        urls = set()
        for p in all_points:
            payload = getattr(p, "payload", None) or {}
            u = payload.get("url", "")
            if u:
                urls.add(u)
        msg = f"Indexed {len(urls)} papers."
        logger.info("Idea RAG Engine: %s", msg)
        return msg

    async def query(self, query: str, limit: int = 30) -> str:
        """
        语义检索，返回 [Source ID: i] (Title)\ntext 格式。
        """
        if not self._init():
            return "Error: RAG not available"
        try:
            logger.info("Idea RAG Engine: query limit=%d text=%r", limit, (query or "")[:200])
            vector = self._encoder.encode(query).tolist()
            result = self._client.query_points(
                collection_name=self.COLLECTION_NAME, query_vector=vector, limit=limit
            )
            lines = []
            for i, p in enumerate(result.points):
                payload = p.payload or {}
                title = payload.get("title", "Unknown")
                text = payload.get("text", "")
                lines.append(f"[Source ID: {i}] (Title: {title})\n{text}")
            out = "\n\n".join(lines) if lines else "No relevant chunks found."
            logger.info("Idea RAG Engine: query result chars=%d", len(out))
            return out
        except Exception as e:
            logger.warning("RAG query failed: %s", e)
            return f"Error: {str(e)}"


def get_rag_engine() -> Optional[IdeaRAGEngine]:
    """获取 RAG 引擎实例，依赖不可用时返回 None。"""
    if not _ensure_imports():
        return None
    return IdeaRAGEngine()
