"""
Jessie — backend/gateway/semantic_cache.py
ChromaDB-backed semantic cache to eliminate duplicate Claude API calls.

How it works:
  - Every prompt is embedded and stored with its response in a per-workspace
    ChromaDB collection named  cache_{workspace_id}.
  - On each new request, search_similar() queries the collection.
    If the nearest neighbour has cosine similarity ≥ threshold (default 0.92),
    the cached response is returned immediately — no Claude call, no cost.
  - embed_and_store() is called after every successful Claude response so
    future similar prompts benefit.
  - clear_old(days=7) removes stale entries; call from a scheduled job or
    on backend startup.

ChromaDB stores distance (0 = identical, 1 = orthogonal).
We convert:  similarity = 1.0 - distance
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CHROMA_PATH = Path(".jessie/chroma_cache")


class SemanticCache:
    """
    Per-workspace ChromaDB semantic cache.
    Each workspace gets its own isolated collection so there is
    zero cross-project leakage of cached responses.
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self._collection_name = f"cache_{workspace_id}"
        self._client = self._make_client()
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def search_similar(self, prompt: str, threshold: float = 0.92) -> Optional[str]:
        """
        Search for a semantically similar cached response.

        Returns the cached response string if the nearest neighbour has
        cosine similarity ≥ threshold, otherwise None.

        ChromaDB returns cosine *distance* (lower = more similar).
        We convert:  similarity = 1.0 - distance
        """
        try:
            if self._collection.count() == 0:
                return None

            results = self._collection.query(
                query_texts=[prompt],
                n_results=1,
                include=["metadatas", "distances"],
            )

            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

            if not distances:
                return None

            similarity = 1.0 - distances[0]
            if similarity >= threshold:
                response = metadatas[0].get("response", "")
                logger.info(
                    f"Cache HIT  workspace={self.workspace_id} "
                    f"similarity={similarity:.4f}"
                )
                return response

            logger.debug(
                f"Cache MISS workspace={self.workspace_id} "
                f"best_similarity={similarity:.4f} threshold={threshold}"
            )
            return None

        except Exception as e:
            logger.warning(f"Cache search failed (non-fatal): {e}")
            return None

    def embed_and_store(
        self,
        prompt: str,
        response: str,
        user_id: str,
        workspace_id: str,
    ) -> None:
        """
        Store a prompt → response pair in the semantic cache.
        The prompt text is the document (ChromaDB embeds it for future search).
        The response is stored in metadata alongside audit fields.
        """
        doc_id = hashlib.md5(
            f"{workspace_id}:{prompt}".encode()
        ).hexdigest()

        try:
            self._collection.upsert(
                ids=[doc_id],
                documents=[prompt],
                metadatas=[{
                    "response":     response[:4000],   # cap metadata size
                    "user_id":      user_id,
                    "workspace_id": workspace_id,
                    "timestamp":    datetime.now(timezone.utc).isoformat(),
                }],
            )
            logger.debug(f"Cache STORE workspace={workspace_id} doc_id={doc_id}")
        except Exception as e:
            logger.warning(f"Cache write failed (non-fatal): {e}")

    def clear_old(self, days: int = 7) -> int:
        """
        Delete cache entries older than `days` days.
        Returns the count of entries removed.
        Safe to call at startup or on a schedule — failure is non-fatal.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()

        try:
            all_items = self._collection.get(include=["metadatas"])
            ids_to_delete = [
                id_
                for id_, meta in zip(
                    all_items.get("ids", []),
                    all_items.get("metadatas", []),
                )
                if meta.get("timestamp", "9999") < cutoff
            ]
            if ids_to_delete:
                self._collection.delete(ids=ids_to_delete)
            logger.info(
                f"Cache GC: removed {len(ids_to_delete)} entries "
                f"older than {days} days"
            )
            return len(ids_to_delete)
        except Exception as e:
            logger.warning(f"Cache clear failed (non-fatal): {e}")
            return 0

    # ── Private ────────────────────────────────────────────────────────────

    def _make_client(self):
        """Create or open the persistent ChromaDB client."""
        try:
            import chromadb
            _CHROMA_PATH.mkdir(parents=True, exist_ok=True)
            return chromadb.PersistentClient(path=str(_CHROMA_PATH))
        except ImportError:
            raise ImportError(
                "chromadb not installed. Run: pip install chromadb"
            )
