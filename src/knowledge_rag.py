"""Local Xtended Space knowledge retrieval (BM25, offline, no LLM)."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from paths import PROJECT_ROOT, load_project_env

load_project_env()

DEFAULT_KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
DEFAULT_INDEX_DIR = PROJECT_ROOT / ".knowledge_index"
MANIFEST_NAME = "manifest.json"
CHUNKS_NAME = "chunks.json"

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u0900-\u097F]+", re.IGNORECASE)


def _cfg_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def knowledge_enabled() -> bool:
    return _cfg_bool("KNOWLEDGE_ENABLED", True)


def knowledge_dir() -> Path:
    raw = (os.getenv("KNOWLEDGE_DIR") or "knowledge").strip()
    p = Path(raw)
    return p if p.is_absolute() else PROJECT_ROOT / p


def index_dir() -> Path:
    raw = (os.getenv("KNOWLEDGE_INDEX_DIR") or ".knowledge_index").strip()
    p = Path(raw)
    return p if p.is_absolute() else PROJECT_ROOT / p


def knowledge_top_k() -> int:
    try:
        return max(1, min(8, int(os.getenv("KNOWLEDGE_TOP_K", "4"))))
    except ValueError:
        return 4


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def source_files_hash(source_dir: Path) -> str:
    h = hashlib.sha256()
    files = sorted(source_dir.glob("*.md"))
    for f in files:
        h.update(f.name.encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]


def chunk_markdown(path: Path) -> list[dict]:
    """Split a markdown file into ## section chunks."""
    text = path.read_text(encoding="utf-8")
    category = path.stem
    parts = re.split(r"(?m)^(## .+)$", text)
    chunks: list[dict] = []

    # Preface before first ##
    preface = (parts[0] or "").strip()
    if preface and not preface.startswith("#"):
        pass
    if preface:
        # Keep H1 + intro as one chunk if substantial
        body = preface
        if len(tokenize(body)) >= 8:
            chunks.append(
                {
                    "id": f"{category}__intro",
                    "category": category,
                    "topic": f"{category}_intro",
                    "source": path.name,
                    "content": body.strip(),
                }
            )

    i = 1
    while i + 1 < len(parts):
        heading = parts[i].strip()
        body = (parts[i + 1] or "").strip()
        i += 2
        topic = re.sub(r"^##\s*", "", heading).strip()
        topic_slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_") or "section"
        content = f"{heading}\n\n{body}".strip()
        if len(tokenize(content)) < 6:
            continue
        chunks.append(
            {
                "id": f"{category}__{topic_slug}",
                "category": category,
                "topic": topic_slug,
                "source": path.name,
                "content": content,
            }
        )
    return chunks


def build_chunks(source_dir: Path) -> list[dict]:
    chunks: list[dict] = []
    for path in sorted(source_dir.glob("*.md")):
        chunks.extend(chunk_markdown(path))
    # stable ids already; ensure uniqueness
    seen: set[str] = set()
    out = []
    for c in chunks:
        cid = c["id"]
        if cid in seen:
            c = dict(c)
            c["id"] = f"{cid}_{len(seen)}"
        seen.add(c["id"])
        out.append(c)
    return out


class BM25Index:
    """Minimal Okapi BM25 over tokenized documents (stdlib only)."""

    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = documents
        self.N = len(documents)
        self.doc_len = [len(d) for d in documents]
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0
        self.df: dict[str, int] = {}
        self.tf: list[dict[str, int]] = []
        for doc in documents:
            counts: dict[str, int] = {}
            for t in doc:
                counts[t] = counts.get(t, 0) + 1
            self.tf.append(counts)
            for t in counts:
                self.df[t] = self.df.get(t, 0) + 1

    def idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        # BM25+ style smooth idf
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def score(self, query_tokens: list[str], index: int) -> float:
        if self.N == 0 or self.avgdl == 0:
            return 0.0
        score = 0.0
        dl = self.doc_len[index]
        tfs = self.tf[index]
        for term in query_tokens:
            if term not in tfs:
                continue
            freq = tfs[term]
            denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += self.idf(term) * (freq * (self.k1 + 1)) / denom
        return score

    def ranked(self, query_tokens: list[str], top_k: int) -> list[tuple[int, float]]:
        if not query_tokens or self.N == 0:
            return []
        scored = [(i, self.score(query_tokens, i)) for i in range(self.N)]
        scored.sort(key=lambda x: x[1], reverse=True)
        out = [(i, s) for i, s in scored if s > 0]
        return out[:top_k]


@dataclass
class RetrievedChunk:
    id: str
    topic: str
    category: str
    source: str
    content: str
    score: float

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "category": self.category,
            "source": self.source,
            "content": self.content,
            "score": round(self.score, 4),
        }


def prepare_query(transcript: str, max_chars: int = 4000) -> str:
    """Lightweight local preprocessing — no LLM."""
    if not transcript:
        return ""
    # Drop timestamps like [00:12-00:20]
    text = re.sub(r"\[\d{1,2}:\d{2}-\d{1,2}:\d{2}\]", " ", transcript)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[: max_chars // 2] + " " + text[-max_chars // 2 :]
    return text


def write_index(source_dir: Path, out_dir: Path) -> dict:
    source_dir = source_dir.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = build_chunks(source_dir)
    if not chunks:
        raise RuntimeError(f"No knowledge chunks found in {source_dir}")

    src_hash = source_files_hash(source_dir)
    manifest = {
        "version": 1,
        "method": "bm25",
        "source_hash": src_hash,
        "chunk_count": len(chunks),
        "sources": sorted(p.name for p in source_dir.glob("*.md")),
        "built_at_unix": int(time.time()),
    }

    (out_dir / CHUNKS_NAME).write_text(
        json.dumps({"chunks": chunks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


class KnowledgeRetriever:
    """
    Loads persistent BM25 index once; retrieves top_k compact chunks per call.
    Offline — no network, no LLM.
    """

    def __init__(self):
        self.enabled = knowledge_enabled()
        self.ready = False
        self.method = "bm25"
        self.chunk_count = 0
        self.source_hash = ""
        self._chunks: list[dict] = []
        self._bm25: BM25Index | None = None
        self._load_error: str | None = None

    def load(self, require: bool = False) -> bool:
        """
        Load index from disk into memory once.
        Returns True if ready. On failure: safe fallback unless require=True.
        """
        self.enabled = knowledge_enabled()
        if not self.enabled:
            self.ready = False
            self._load_error = "KNOWLEDGE_ENABLED=false"
            return False

        try:
            src = knowledge_dir()
            idx = index_dir()
            manifest_path = idx / MANIFEST_NAME
            chunks_path = idx / CHUNKS_NAME

            if not manifest_path.exists() or not chunks_path.exists():
                if src.exists() and any(src.glob("*.md")):
                    write_index(src, idx)
                else:
                    raise FileNotFoundError(
                        f"Knowledge index missing at {idx}. "
                        "Run: python scripts/build_knowledge_index.py"
                    )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload = json.loads(chunks_path.read_text(encoding="utf-8"))
            chunks = payload.get("chunks") or []
            if not chunks:
                raise RuntimeError("Knowledge index has zero chunks")

            current_hash = source_files_hash(src) if src.exists() else ""
            stored_hash = str(manifest.get("source_hash") or "")
            if current_hash and stored_hash and current_hash != stored_hash:
                # Stale index — rebuild automatically once at load time only
                write_index(src, idx)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                payload = json.loads(chunks_path.read_text(encoding="utf-8"))
                chunks = payload.get("chunks") or []

            docs = [tokenize(c.get("content", "")) for c in chunks]
            self._chunks = chunks
            self._bm25 = BM25Index(docs)
            self.chunk_count = len(chunks)
            self.source_hash = str(manifest.get("source_hash") or "")
            self.method = str(manifest.get("method") or "bm25")
            self.ready = True
            self._load_error = None
            return True

        except Exception as e:
            self.ready = False
            self._load_error = str(e)
            if require:
                raise
            return False

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def retrieve(self, transcript: str, top_k: int | None = None) -> list[RetrievedChunk]:
        if not self.ready or self._bm25 is None:
            return []

        k = top_k if top_k is not None else knowledge_top_k()
        query = prepare_query(transcript)
        tokens = tokenize(query)
        if not tokens:
            return []

        ranked = self._bm25.ranked(tokens, k)
        results: list[RetrievedChunk] = []
        for idx, score in ranked:
            c = self._chunks[idx]
            results.append(
                RetrievedChunk(
                    id=c["id"],
                    topic=c.get("topic", ""),
                    category=c.get("category", ""),
                    source=c.get("source", ""),
                    content=c.get("content", "").strip(),
                    score=float(score),
                )
            )
        return results

    def format_for_prompt(self, chunks: Iterable[RetrievedChunk]) -> str:
        blocks = []
        for i, ch in enumerate(chunks, start=1):
            blocks.append(
                f"[{i}] topic={ch.topic} source={ch.source}\n{ch.content}"
            )
        return "\n\n".join(blocks).strip()


# Process-wide singleton loaded once at worker startup
_retriever: KnowledgeRetriever | None = None


def get_retriever() -> KnowledgeRetriever:
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever


def init_knowledge(require: bool = False) -> KnowledgeRetriever:
    """Call once at worker startup."""
    r = get_retriever()
    r.load(require=require)
    return r
