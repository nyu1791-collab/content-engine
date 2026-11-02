import os
import tempfile
import unittest
from pathlib import Path
from tests import network_guard  # noqa: F401
from unittest.mock import Mock, patch

from engine import __main__ as app, approval, state

ENV = {"DISCORD_BOT_TOKEN": "test-token", "DISCORD_APPROVAL_CHANNEL_ID": "111", "DISCORD_APPROVER_ID": "222"}


def reply(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        for p in (patch.object(state, "PATH", self.path / "state.json"),
                  patch.object(app.writer, "thread", return_value=["確認用"]),
                  patch.dict(os.environ, ENV)):
            p.start()
            self.addCleanup(p.stop)
        self.st = {"seen": {}, "queue": [], "posts": []}
        self.cfg = {"output_dir": str(self.path / "output"), "publishers": [], "wp_status": "draft", "approval": True}
        self.post = {"title": "記事", "slug": "test", "body": "本文", "tags": [],
                     "source_url": "https://source.example/article"}

    def test_decisions_accept_only_approver_and_waiting_ids(self):
        # Discord は新しい順で返す。承認者以外と対象外のIDは無視する。
        messages = [
            {"author": {"id": "999"}, "content": "承認 aaaaaaaaaaaa"},
            {"author": {"id": "222"}, "content": "承認 aaaaaaaaaaaa"},
            {"author": {"id": "222"}, "content": "却下 aaaaaaaaaaaa"},
            {"author": {"id": "222"}, "content": "却下 bbbbbbbbbbbb"},
            {"author": {"id": "222"}, "content": "承認 cccccccccccc"},
        ]
        with patch("engine.approval.requests.request", return_value=reply(messages)):
            decided = approval.decisions({"aaaaaaaaaaaa", "bbbbbbbbbbbb"})
        self.assertEqual(decided, {"aaaaaaaaaaaa": "approved", "bbbbbbbbbbbb": "rejected"})

    def test_request_mentions_only_the_approver_and_returns_message_id(self):
        record = {"id": "0123456789ab", "post": self.post}
        with patch("engine.approval.requests.request", return_value=reply({"id": "999"})) as call:
            message_id = approval.request(record)
        self.assertEqual(message_id, "999")
        payload = call.call_args.kwargs["json"]
        self.assertEqual(payload["allowed_mentions"], {"users": ["222"]})
        self.assertTrue(payload["content"].startswith("<@222> "))
        self.assertIn("承認 0123456789ab", payload["content"])

    def test_post_waits_for_approval_before_publishing(self):
        with patch("engine.approval.requests.request", return_value=reply({"id": "999"})):
            record = app.publish(self.post, self.cfg, self.st)
            self.assertEqual(record["approval"]["status"], "pending")
            self.assertFalse(Path(self.cfg["output_dir"]).exists())
            with patch.object(approval, "decisions", return_value={}):
                app.do_approve(self.cfg, self.st)
        self.assertEqual(record["approval"]["message_id"], "999")
        self.assertFalse(Path(self.cfg["output_dir"]).exists())  # まだ判定がない

    def test_rejected_post_is_never_published(self):
        with patch("engine.approval.requests.request", return_value=reply({"id": "999"})):
            record = app.publish(self.post, self.cfg, self.st)
            with patch.object(approval, "decisions", return_value={record["id"]: "rejected"}):
                app.do_approve(self.cfg, self.st)
            with patch.object(approval, "decisions", return_value={record["id"]: "approved"}):
                app.do_approve(self.cfg, self.st)  # 却下済みは判定し直さない
        self.assertEqual(record["approval"]["status"], "rejected")
        self.assertFalse(Path(self.cfg["output_dir"]).exists())

    def test_approved_post_is_published_after_decision(self):
        with patch("engine.approval.requests.request", return_value=reply({"id": "999"})):
            record = app.publish(self.post, self.cfg, self.st)
            with patch.object(approval, "decisions", return_value={record["id"]: "approved"}):
                app.do_approve(self.cfg, self.st)
        self.assertEqual(record["approval"]["status"], "approved")
        self.assertEqual(record["deliveries"]["file"]["status"], "succeeded")
        self.assertIn("本文", Path(record["deliveries"]["file"]["url"]).read_text(encoding="utf-8"))

    def test_missing_settings_publish_nothing(self):
        with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": ""}):
            record = app.publish(self.post, self.cfg, self.st)
            app.do_approve(self.cfg, self.st)
        self.assertEqual(record["approval"]["status"], "pending")
        self.assertIn("DISCORD_BOT_TOKEN", record["approval"]["error"])
        self.assertFalse(Path(self.cfg["output_dir"]).exists())


if __name__ == "__main__":
    unittest.main()
