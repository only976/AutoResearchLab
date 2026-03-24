"""
Idea Agent PDF RAG 引擎 - 将筛选后的论文 PDF 正文向量化并支持语义检索。
向量库通过 shared.vector_store 抽象，支持 Qdrant / Cloudflare Vectorize。
"""

import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger
from shared.vector_store import VectorRecord, create_vector_store

# 延迟导入，依赖可选
_SentenceTransformer = None
_PdfReader = None


def _ensure_imports() -> bool:
    """延迟加载 RAG 依赖，失败时返回 False。"""
    global _SentenceTransformer, _PdfReader
    if _SentenceTransformer is not None:
        return True
    try:
        from pypdf import PdfReader as _PR
        from sentence_transformers import SentenceTransformer as _ST

        globals()["_SentenceTransformer"] = _ST
        globals()["_PdfReader"] = _PR
        return True
    except ImportError as e:
        logger.debug("RAG dependencies not available: %s", e)
        return False


class IdeaRAGEngine:
    """PDF 向量检索引擎，用于 Idea Agent 精细 refine。"""

    COLLECTION_NAME = "academic_chunks"
    CONCEPT_COLLECTION_NAME = "concept_chunks"
    VECTOR_SIZE = 384
    MAX_PAGES = 10
    CHUNK_CHARS = 1000

    def __init__(self, qdrant_path: Optional[Path] = None, papers_collection: Optional[str] = None):
        """
        初始化 RAG 引擎。
        qdrant_path: 本地 Qdrant 存储路径（仅 provider=qdrant 时使用）。
        """
        self._store = None
        self._encoder = None
        self._initialized = False
        self._qdrant_path = qdrant_path
        self._cache_dir: Optional[Path] = None
        self._papers_collection = papers_collection or os.getenv("CF_VECTORIZE_REFINE_INDEX") or self.COLLECTION_NAME
        self._concept_collection = os.getenv("CF_VECTORIZE_CONCEPT_INDEX") or self.CONCEPT_COLLECTION_NAME

    def _init(self) -> bool:
        """延迟初始化，依赖可用时返回 True。"""
        if self._initialized:
            return self._store is not None
        if not _ensure_imports():
            return False
        try:
            from sentence_transformers import SentenceTransformer

            path = self._qdrant_path or (Path(__file__).resolve().parent.parent / "db" / "qdrant")
            path.mkdir(parents=True, exist_ok=True)
            self._store = create_vector_store(qdrant_local_path=path)
            self._store.ensure_collection(self._papers_collection, self.VECTOR_SIZE)
            self._store.ensure_collection(self._concept_collection, self.VECTOR_SIZE)

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

    def _get_pdf_chunks_from_local(self, pdf_path: Path) -> List[Dict]:
        """从本地 PDF 读取并提取前 N 页文本（用于概念知识库）。"""
        if not pdf_path.exists() or not pdf_path.is_file():
            return []
        if not _ensure_imports():
            return []

        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(pdf_path))
            chunks: List[Dict] = []
            for i, page in enumerate(reader.pages[: self.MAX_PAGES]):
                text = page.extract_text() if hasattr(page, "extract_text") else None
                if text:
                    chunks.append(
                        {
                            "content": text.replace("\n", " ")[: self.CHUNK_CHARS],
                            "page": i + 1,
                        }
                    )
            return chunks
        except Exception as e:
            logger.debug("Local PDF extract failed for {}: {}", str(pdf_path)[:120], e)
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
        all_points: list[VectorRecord] = []
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
                    VectorRecord(
                        id=point_id,
                        vector=vector,
                        payload={"title": title, "text": content, "page": c.get("page", 0), "url": url},
                    )
                )
        if not all_points:
            logger.info("Idea RAG Engine: no chunks extracted from PDFs")
            return "No papers indexed (no PDF content extracted)."
        self._store.reset_collection(self._papers_collection, self.VECTOR_SIZE)
        self._store.upsert(self._papers_collection, all_points)
        urls = set()
        for p in all_points:
            payload = getattr(p, "payload", None) or {}
            u = payload.get("url", "")
            if u:
                urls.add(u)
        msg = f"Indexed {len(urls)} papers."
        logger.info("Idea RAG Engine: %s", msg)
        return msg

    async def index_concepts(
        self,
        concepts_dir: Optional[Path] = None,
        *,
        reset_collection: bool = True,
        max_files: int = 100,
    ) -> str:
        """索引“概念知识库”PDF 到独立向量集合。

        concepts_dir:
          - None: 使用环境变量 `MAARS_CONCEPTS_PDFS_DIR`；
          - 否则使用默认目录 `backend/db/concepts_pdfs`。
        """
        if not self._init():
            return "Error: RAG dependencies not available (qdrant-client, sentence-transformers, pypdf)"

        concepts_dir = concepts_dir or os.getenv("MAARS_CONCEPTS_PDFS_DIR")
        if concepts_dir:
            concepts_dir = Path(concepts_dir)
        else:
            concepts_dir = Path(__file__).resolve().parent.parent / "db" / "concepts_pdfs"

        if not concepts_dir.exists() or not concepts_dir.is_dir():
            return f"No concept KB dir found: {str(concepts_dir)}"

        pdfs = sorted([p for p in concepts_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])
        if not pdfs:
            return f"No concept PDFs found in: {str(concepts_dir)}"
        pdfs = pdfs[: max_files]

        all_points: list[VectorRecord] = []
        for pdf_path in pdfs:
            title = pdf_path.stem or "concept"
            chunks = self._get_pdf_chunks_from_local(pdf_path)
            if not chunks:
                continue
            for idx, c in enumerate(chunks):
                content = c.get("content", "")
                if not content.strip():
                    continue
                vector = self._encoder.encode(content).tolist()
                point_id = hashlib.md5(f"{title}_{idx}_{str(pdf_path)}".encode()).hexdigest()
                all_points.append(
                    VectorRecord(
                        id=point_id,
                        vector=vector,
                        payload={
                            "title": title,
                            "text": content,
                            "page": c.get("page", 0),
                            "url": str(pdf_path),
                        },
                    )
                )

        if not all_points:
            logger.info("Idea RAG Engine: no concept chunks extracted")
            return "No concept KB indexed (no chunks extracted)."

        if reset_collection:
            self._store.reset_collection(self._concept_collection, self.VECTOR_SIZE)
        else:
            self._store.ensure_collection(self._concept_collection, self.VECTOR_SIZE)
        self._store.upsert(self._concept_collection, all_points)
        msg = f"Indexed {len(pdfs)} concept PDFs into {self._concept_collection}."
        logger.info("Idea RAG Engine: %s", msg)
        return msg

    async def query_concepts(self, query: str, limit: int = 30) -> str:
        """在“概念知识库”集合中做语义检索。"""
        if not self._init():
            return "Error: RAG not available"
        try:
            q = (query or "").strip()
            if not q:
                return "Error: query required"

            logger.info(
                "Idea RAG Engine: query_concepts collection=%s limit=%d query=%r",
                self._concept_collection,
                limit,
                q[:200],
            )
            vector = self._encoder.encode(q).tolist()
            result = self._store.query(self._concept_collection, vector, limit)
            lines = []
            for i, p in enumerate(result):
                payload = p.get("payload") or {}
                title = payload.get("title", "Unknown")
                text = payload.get("text", "")
                lines.append(f"[Source ID: {i}] (Concept: {title})\n{text}")
            return "\n\n".join(lines) if lines else "No relevant concept chunks found."
        except Exception as e:
            logger.warning("RAG concept query failed: %s", e)
            return f"Error: {str(e)}"

    async def query(self, query: str, limit: int = 30) -> str:
        """
        语义检索，返回 [Source ID: i] (Title)\ntext 格式。
        """
        if not self._init():
            return "Error: RAG not available"
        try:
            logger.info("Idea RAG Engine: query limit=%d text=%r", limit, (query or "")[:200])
            vector = self._encoder.encode(query).tolist()
            result = self._store.query(self._papers_collection, vector, limit)
            lines = []
            for i, p in enumerate(result):
                payload = p.get("payload") or {}
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
