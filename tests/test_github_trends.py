"""Tests für scripts/github_trends.py (offline, nur Standardbibliothek).

Aufruf: python -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import github_trends as gt  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "trending_weekly.html"


class ParseTest(unittest.TestCase):
    def test_parses_all_fields(self):
        repos = gt.parse_trending(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(repos), 14)
        first = repos[0]
        self.assertEqual(first["name"], "acme/agent-kit")
        self.assertEqual(first["url"], "https://github.com/acme/agent-kit")
        self.assertEqual(first["stars_week"], 3120)
        self.assertEqual(first["stars_total"], 18450)
        self.assertEqual(first["language"], "Python")
        self.assertIn("&", repos[2]["description"])  # HTML-Entities aufgelöst
        empty = repos[-1]
        self.assertIsNone(empty["description"])
        self.assertIsNone(empty["language"])


class FilterTest(unittest.TestCase):
    def test_keywords(self):
        for text in ["AI-powered app", "Fine-tuning LLMs", "MCP server", "Claude Code skills",
                     "stable diffusion", "Hugging Face hub", "gpt-oss"]:
            self.assertIsNotNone(gt.ai_match(text), text)
        for text in ["maintain html files", "A fast YAML parser", "Web framework for Go",
                     "User-Agent string parser", "ssh-agent forwarding"]:
            self.assertIsNone(gt.ai_match(text), text)

    def test_top10_sorted_ai_only(self):
        repos, candidates = gt.collect([FIXTURE.read_text(encoding="utf-8")], token=None)
        names = [r["name"] for r in repos]
        self.assertEqual(candidates, 14)
        self.assertEqual(len(repos), 10)
        self.assertNotIn("foo/fast-yaml", names)
        self.assertNotIn("qux/ua-parser", names)
        self.assertNotIn("z/web-framework", names)
        weeks = [r["stars_week"] for r in repos]
        self.assertEqual(weeks, sorted(weeks, reverse=True))


class MainTest(unittest.TestCase):
    def test_writes_contract_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "github.json"
            self.assertEqual(gt.main(["--html", str(FIXTURE), "--out", str(out)]), 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertRegex(data["generated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertEqual(len(data["repos"]), 10)
            for r in data["repos"]:
                for key in ["name", "url", "description", "stars_week", "language"]:
                    self.assertIn(key, r)
                self.assertIsInstance(r["stars_week"], int)

    def test_keeps_old_file_when_too_few(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "github.json"
            out.write_text('{"alt": true}', encoding="utf-8")
            empty = Path(tmp) / "empty.html"
            empty.write_text("<html></html>", encoding="utf-8")
            self.assertEqual(gt.main(["--html", str(empty), "--out", str(out)]), 1)
            self.assertEqual(out.read_text(encoding="utf-8"), '{"alt": true}')


if __name__ == "__main__":
    unittest.main()
