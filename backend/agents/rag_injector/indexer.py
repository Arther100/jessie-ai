"""
Jessie — backend/agents/rag_injector/indexer.py
Per-workspace ChromaDB index.
Rebuilds automatically when stale (>10 min old).
Scoped by workspace_id — projects never share an index.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict
from datetime import datetime, timedelta

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

INDEXABLE = {".py",".ts",".tsx",".js",".jsx",".java",".go",".rs",".html",".css",".md"}
SKIP_DIRS = {"node_modules",".git","__pycache__",".venv","venv","dist","build",".next","coverage","out"}
MAX_FILE_KB = 50


class CodebaseIndexer:
    def __init__(self, workspace_id: str):
        self.workspace_id  = workspace_id
        self.collection_id = f"jessie_{workspace_id}"
        self.meta_path     = Path(f".jessie/index_meta_{workspace_id}.json")

        if CHROMA_AVAILABLE:
            self.client     = chromadb.PersistentClient(path=".jessie/chroma")
            self.ef         = embedding_functions.DefaultEmbeddingFunction()
            self.collection = self.client.get_or_create_collection(
                name=self.collection_id,
                embedding_function=self.ef,
            )

    def build_if_stale(self, root: str = "."):
        if not CHROMA_AVAILABLE:
            return
        meta      = self._load_meta()
        last_built = meta.get("last_built")
        if last_built:
            if datetime.now() - datetime.fromisoformat(last_built) < timedelta(minutes=10):
                return
        self._build(root)

    def search(self, query: str, top_k: int = 4) -> List[Dict]:
        if not CHROMA_AVAILABLE:
            return []
        try:
            results = self.collection.query(query_texts=[query], n_results=top_k)
            return [
                {"file": m["file"], "content": d}
                for d, m in zip(results["documents"][0], results["metadatas"][0])
            ]
        except Exception:
            return []

    def _build(self, root: str):
        files = self._collect(root)
        docs, metas, ids = [], [], []
        for fp in files:
            try:
                text   = Path(fp).read_text(encoding="utf-8", errors="ignore")
                chunks = self._chunk(text, 500, 50)
                for i, chunk in enumerate(chunks):
                    uid = hashlib.md5(f"{fp}:{i}".encode()).hexdigest()
                    docs.append(chunk)
                    metas.append({"file": fp, "chunk": i})
                    ids.append(uid)
            except Exception:
                continue
        if docs:
            for i in range(0, len(docs), 100):
                self.collection.upsert(
                    documents=docs[i:i+100],
                    metadatas=metas[i:i+100],
                    ids=ids[i:i+100],
                )
        self._save_meta({"last_built": datetime.now().isoformat(), "files": len(files)})

    def _collect(self, root: str) -> List[str]:
        result = []
        for dp, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if Path(f).suffix not in INDEXABLE:
                    continue
                full = os.path.join(dp, f)
                if os.path.getsize(full) > MAX_FILE_KB * 1024:
                    continue
                result.append(full)
        return result

    def _chunk(self, text: str, size: int, overlap: int) -> List[str]:
        chunks, start = [], 0
        while start < len(text):
            chunks.append(text[start:start+size])
            start += size - overlap
        return chunks

    def _load_meta(self) -> dict:
        if self.meta_path.exists():
            return json.loads(self.meta_path.read_text())
        return {}

    def _save_meta(self, meta: dict):
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(json.dumps(meta))
