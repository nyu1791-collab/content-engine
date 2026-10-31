"""promo: 下書き→（手直し）→投稿、ローテーション、成人向け表記。外部通信なし。"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import network_guard  # noqa: F401
from engine import promo, state


class PromoTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.d = Path(t.name)
        p = patch.object(state, "PATH", self.d / "state.json"); p.start(); self.addCleanup(p.stop)
        self.cat = self.d / "c.csv"
        self.cat.write_text("title,url,langs,blurb,tags,adult\nWork A,https://w.invalid/a,\"en,zh-Hans\",Desc,\"manga\",1\n", encoding="utf-8")
        self.cfg = {"output_dir": str(self.d / "out")}
        self.st = {"seen": {}, "queue": [], "posts": []}

    def run_promo(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(promo.llm, "ask", return_value=None):
            return promo.run(self.cat, self.st, self.cfg, **kw)

    def test_draft_then_publish_uses_edited_text_and_rotates(self):
        made = self.run_promo()
        self.assertEqual(len(made), 2)
        self.assertTrue(all(m["text"].startswith("[18+]") for m in made))
        f = Path(made[0]["file"]); rec = json.loads(f.read_text(encoding="utf-8")); rec["text"] = "[18+] edited https://w.invalid/a"
        f.write_text(json.dumps(rec), encoding="utf-8")
        with patch("engine.publishers.x.post_thread", return_value="https://x.com/i/status/1") as post:
            made = self.run_promo(publish=True)
        self.assertEqual(post.call_args_list[0][0][0], ["[18+] edited https://w.invalid/a"])
        self.assertEqual({m["status"] for m in made}, {"posted"})
        with patch("engine.publishers.x.post_thread") as post:
            self.assertEqual(self.run_promo(publish=True), [])   # 7日以内は再投稿しない
            post.assert_not_called()
