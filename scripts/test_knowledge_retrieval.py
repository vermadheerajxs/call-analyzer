#!/usr/bin/env python
"""Quick offline retrieval smoke checks (no Ollama, no recordings).

Usage (from repo root):
  python scripts/test_knowledge_retrieval.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from knowledge_rag import init_knowledge, write_index, knowledge_dir, index_dir  # noqa: E402


CASES = [
    (
        "storage",
        "mujhe ghar ka saman kuch mahine ke liye rakhna hai furniture storage",
        ("storage", "household", "saman", "services"),
    ),
    (
        "relocation",
        "ghar shift karna hai packers movers relocation",
        ("shift", "reloc", "packer", "mover", "services"),
    ),
    (
        "support_pickup",
        "mera pickup kal hona tha abhi tak koi nahi aaya delayed pickup",
        ("pickup", "support", "delay", "logistics", "complaint"),
    ),
    (
        "b2b",
        "warehouse mein stock rakhna hai business inventory storage",
        ("warehouse", "b2b", "stock", "inventory", "business"),
    ),
]


def main() -> int:
    # Ensure index exists for this smoke test
    write_index(knowledge_dir(), index_dir())
    r = init_knowledge(require=True)
    print(
        f"Loaded method={r.method} chunks={r.chunk_count} hash={r.source_hash}"
    )

    failed = 0
    for name, query, needles in CASES:
        hits = r.retrieve(query, top_k=4)
        blob = " ".join(
            f"{h.topic} {h.category} {h.source} {h.content}".lower() for h in hits
        )
        ok = any(n.lower() in blob for n in needles)
        topics = [h.topic for h in hits]
        status = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{status}] {name}: topics={topics}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
