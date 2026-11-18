"""Tests für scripts/ideas.py. Start: python -m unittest discover tests"""

import json
import re
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ideas  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


class IdeasTest(unittest.TestCase):
    def setUp(self):
        self.news = ideas.load_news(FIX / "news.json")
        self.repos = ideas.load_github(FIX / "github.json")

    def test_contract_shape(self):
        out = ideas.build_output(self.news, self.repos)
        self.assertRegex(out["generated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(len(out["topics"]), 5)
        for t in out["topics"]:
            for key in ("topic", "short", "carousel", "long_video"):
                self.assertIsInstance(t[key], str)
                self.assertTrue(t[key].strip())
            self.assertLessEqual(len(t["topic"]), 40)
            self.assertIsInstance(t["score"], int)
            self.assertTrue(all(isinstance(s, str) for s in t["sources"]))
        scores = [t["score"] for t in out["topics"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(scores[0], 100)

    def test_ideas_use_real_headlines(self):
        out = ideas.build_output(self.news, self.repos)
        top = out["topics"][0]
        lead_titles = [e.title for e in self.news]
        self.assertTrue(any(title in top["carousel"] for title in lead_titles))

    def test_deterministic_per_day(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 19, 6, 0, tzinfo=timezone.utc)
        a = ideas.build_output(ideas.load_news(FIX / "news.json"), ideas.load_github(FIX / "github.json"), now)
        b = ideas.build_output(ideas.load_news(FIX / "news.json"), ideas.load_github(FIX / "github.json"), now)
        self.assertEqual(a, b)

    def test_works_with_only_one_input(self):
        self.assertEqual(len(ideas.build_output(self.news, [])["topics"]), 5)
        self.assertEqual(len(ideas.build_output([], self.repos)["topics"]), 5)

    def test_fills_up_to_five_topics(self):
        few = [e for e in self.news if "Claude" in e.title][:2] + [
            ideas.Entry("news", "hackernews", "Something entirely unrelated", "Something entirely unrelated",
                        "https://x", "https://x", 10, 1),
        ]
        out = ideas.build_output(few, [])
        self.assertGreaterEqual(len(out["topics"]), 2)

    def test_classification(self):
        e = ideas.Entry("news", "r/artificial", "Running Llama locally with Ollama", "Running Llama locally with Ollama", "", "")
        self.assertEqual(ideas.classify(e), "Lokale KI")
        e = ideas.Entry("news", "r/ClaudeAI", "Usage limits changed again?", "Usage limits changed again?", "", "")
        self.assertEqual(ideas.classify(e), "Claude & Anthropic")

    def test_error_keeps_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "ideas.json"
            out.write_text('{"old": true}', encoding="utf-8")
            rc = ideas.main(["--news", str(Path(d) / "fehlt.json"), "--github", str(Path(d) / "fehlt2.json"),
                             "--out", str(out)])
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {"old": True})

    def test_main_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "ideas.json"
            rc = ideas.main(["--news", str(FIX / "news.json"), "--github", str(FIX / "github.json"), "--out", str(out)])
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["engine"], "template")
            self.assertEqual(len(data["topics"]), 5)

    def test_claude_failure_falls_back_to_templates(self):
        env = {"IDEAS_ENGINE": "claude", "ANTHROPIC_API_KEY": "test"}
        with mock.patch.dict(os.environ, env), mock.patch.object(ideas, "claude_ideas", side_effect=RuntimeError("boom")):
            out = ideas.build_output(self.news, self.repos)
        self.assertEqual(out["engine"], "template")
        self.assertEqual(len(out["topics"]), 5)

    def test_claude_off_by_default(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}, clear=False):
            os.environ.pop("IDEAS_ENGINE", None)
            self.assertFalse(ideas.use_claude())

    def test_repo_description_does_not_make_brand_topic(self):
        # Demo-Fehler: Alibaba-Repo landete unter „Claude & Anthropic“, weil die
        # Beschreibung Claude Code erwähnte.
        repo = ideas.Entry("repo", "github", "QwenLM/qwen-code", "QwenLM qwen-code qwen code", "u", "u",
                           desc="An open-source coding agent, alternative to Claude Code")
        self.assertNotEqual(ideas.classify(repo), "Claude & Anthropic")
        multi = ideas.Entry("repo", "github", "acme/llm-gateway", "acme llm-gateway llm gateway", "u", "u",
                            desc="One API for OpenAI, Claude and Gemini")
        self.assertNotIn(ideas.classify(multi), {"Claude & Anthropic", "OpenAI & ChatGPT", "Google Gemini"})
        own = ideas.Entry("repo", "github", "anthropics/claude-code", "anthropics claude-code claude code", "u", "u",
                          desc="Agentic coding tool")
        self.assertEqual(ideas.classify(own), "Claude & Anthropic")

    def test_brand_topic_never_showcases_foreign_repo(self):
        news = [e for e in self.news if e.source == "r/ClaudeAI"]
        foreign = ideas.Entry("repo", "github", "alibaba/agentscope", "alibaba agentscope agentscope", "u", "u",
                              stars_week=9000, desc="Multi-agent platform, works with Claude")
        out = ideas.build_output(news, [foreign])
        claude = next(t for t in out["topics"] if t["topic"] == "Claude & Anthropic")
        for key in ("short", "carousel", "long_video"):
            self.assertNotIn("alibaba", claude[key])

    def test_templates_read_correctly_for_every_topic(self):
        # Alle Vorlagen-Varianten für alle Katalog-Themen erzeugen und auf
        # typische Grammatik-Brüche prüfen.
        for d in ideas.CATALOG:
            e = ideas.Entry("news", "hackernews", f"Headline about {d.name}", "x", "u", "u", 100, 50)
            t = ideas.Topic(d.name, [e], d)
            f = ideas._facts(t)
            for day in range(40):
                seed = f"2026-11-{day:02d}|{d.name}|"
                text = "\n".join([ideas.idea_short(f, seed), ideas.idea_carousel(f, seed), ideas.idea_long(f, seed)])
                self.assertNotIn("Wenn du", text)
                self.assertNotRegex(text, r"wollen bist|nutzen bist|Was [^.]*, jetzt tun")
                self.assertNotIn("  ", text)
                # Themennamen nur mit Doppelpunkt oder in „…“ einbauen, nie frei im Satz
                # („Warum KI-Agenten gerade explodiert“, „zu Lokale KI“).
                self.assertNotRegex(text, r"(über|zu|Warum|mir) " + re.escape(d.name))


if __name__ == "__main__":
    unittest.main()
