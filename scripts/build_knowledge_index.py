#!/usr/bin/env python
"""Build / rebuild the local Xtended Space knowledge BM25 index.

Usage (from repo root):
  python scripts/build_knowledge_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from knowledge_rag import (  # noqa: E402
    index_dir,
    knowledge_dir,
    write_index,
)


def main() -> int:
    src = knowledge_dir()
    out = index_dir()
    if not src.exists():
        print(f"ERROR: knowledge directory not found: {src}")
        return 1

    manifest = write_index(src, out)
    print("Knowledge index built successfully")
    print(f"  source:  {src}")
    print(f"  index:   {out}")
    print(f"  method:  {manifest['method']}")
    print(f"  chunks:  {manifest['chunk_count']}")
    print(f"  hash:    {manifest['source_hash']}")
    print(f"  files:   {', '.join(manifest['sources'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
