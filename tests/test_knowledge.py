"""Focused tests for Xtended Space local knowledge / BM25 retrieval."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import knowledge_rag as kr  # noqa: E402


class KnowledgeIndexTests(unittest.TestCase):
    def test_build_index_from_project_knowledge(self):
        src = ROOT / "knowledge"
        self.assertTrue(src.exists())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = kr.write_index(src, out)
            self.assertGreater(manifest["chunk_count"], 5)
            self.assertEqual(manifest["method"], "bm25")
            self.assertTrue((out / "chunks.json").exists())
            self.assertTrue((out / "manifest.json").exists())
            payload = json.loads((out / "chunks.json").read_text(encoding="utf-8"))
            self.assertEqual(len(payload["chunks"]), manifest["chunk_count"])


class KnowledgeRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.index_path = Path(cls._tmpdir.name)
        kr.write_index(ROOT / "knowledge", cls.index_path)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def _retriever(self):
        r = kr.KnowledgeRetriever()
        with mock.patch.object(kr, "index_dir", return_value=self.index_path), mock.patch.object(
            kr, "knowledge_dir", return_value=ROOT / "knowledge"
        ), mock.patch.object(kr, "knowledge_enabled", return_value=True):
            ok = r.load(require=True)
        self.assertTrue(ok)
        return r

    def test_storage_query(self):
        r = self._retriever()
        hits = r.retrieve(
            "mujhe ghar ka saman kuch mahine ke liye rakhna hai furniture storage",
            top_k=4,
        )
        blob = " ".join(f"{h.topic} {h.category} {h.content}".lower() for h in hits)
        self.assertTrue(hits)
        self.assertTrue(
            any(x in blob for x in ("storage", "household", "saman", "services"))
        )

    def test_relocation_query(self):
        r = self._retriever()
        hits = r.retrieve(
            "ghar shift karna hai packers movers relocation",
            top_k=4,
        )
        blob = " ".join(f"{h.topic} {h.content}".lower() for h in hits)
        self.assertTrue(
            any(x in blob for x in ("shift", "reloc", "packer", "mover"))
        )

    def test_delayed_pickup_query(self):
        r = self._retriever()
        hits = r.retrieve(
            "mera pickup kal hona tha abhi tak koi nahi aaya delayed pickup",
            top_k=4,
        )
        blob = " ".join(f"{h.topic} {h.category} {h.content}".lower() for h in hits)
        self.assertTrue(
            any(x in blob for x in ("pickup", "support", "delay", "complaint", "logistics"))
        )

    def test_b2b_query(self):
        r = self._retriever()
        hits = r.retrieve(
            "warehouse mein stock rakhna hai business inventory storage",
            top_k=4,
        )
        blob = " ".join(f"{h.topic} {h.category} {h.content}".lower() for h in hits)
        self.assertTrue(
            any(x in blob for x in ("warehouse", "b2b", "stock", "inventory", "business"))
        )

    def test_fallback_missing_index(self):
        r = kr.KnowledgeRetriever()
        missing = Path(self._tmpdir.name) / "does_not_exist_index"
        empty_src = Path(self._tmpdir.name) / "empty_knowledge"
        empty_src.mkdir(exist_ok=True)
        with mock.patch.object(kr, "index_dir", return_value=missing), mock.patch.object(
            kr, "knowledge_dir", return_value=empty_src
        ), mock.patch.object(kr, "knowledge_enabled", return_value=True):
            ok = r.load(require=False)
        self.assertFalse(ok)
        self.assertIsNotNone(r.load_error)
        self.assertEqual(r.retrieve("storage furniture"), [])

    def test_fallback_disabled(self):
        r = kr.KnowledgeRetriever()
        with mock.patch.object(kr, "knowledge_enabled", return_value=False):
            ok = r.load(require=False)
        self.assertFalse(ok)
        self.assertEqual(r.retrieve("storage furniture"), [])

    def test_prompt_injection_helpers(self):
        r = self._retriever()
        hits = r.retrieve("household storage furniture for six months", top_k=2)
        block = r.format_for_prompt(hits)
        self.assertIn("topic=", block)
        self.assertTrue(len(block) > 20)
        # Mimic analyzer prompt assembly
        prompt = f"RELEVANT XTENDED SPACE BUSINESS CONTEXT:\n{block}\n\nTranscript:\nhello"
        self.assertIn("RELEVANT XTENDED SPACE BUSINESS CONTEXT", prompt)
        self.assertIn("Transcript:", prompt)


if __name__ == "__main__":
    unittest.main()
