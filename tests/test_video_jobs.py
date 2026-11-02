import json
import os
import tempfile
import unittest
from pathlib import Path
from tests import network_guard  # noqa: F401
from unittest.mock import Mock, patch

from engine import __main__ as app, approval, state, video_jobs

ENV = {"DISCORD_BOT_TOKEN": "test-token", "DISCORD_APPROVAL_CHANNEL_ID": "111", "DISCORD_APPROVER_ID": "222"}


def reply(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class VideoJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.jobs = self.path / "jobs"
        for p in (patch.object(state, "PATH", self.path / "state.json"),
                  patch.dict(os.environ, {**ENV, "VIDEO_JOB_DIR": str(self.jobs)})):
            p.start()
            self.addCleanup(p.stop)
        self.st = {"seen": {}, "queue": [], "posts": []}
        self.cfg = {"publishers": [], "wp_status": "draft"}

    def run_video(self, topic, urls, decision):
        """テーマを登録して承認依頼を送り、decision（approved/rejected/None=未判定）を反映する。"""
        with patch("engine.approval.requests.request", return_value=reply({"id": "999"})) as call:
            with patch.object(approval, "decisions", return_value={}):
                app.do_video(self.cfg, self.st, topic, urls)
            record = self.st["posts"][-1]
            decided = {record["id"]: decision} if decision else {}
            with patch.object(approval, "decisions", return_value=decided):
                app.do_approve(self.cfg, self.st)
        return record, call

    def test_request_rejects_empty_topic_and_non_https_url(self):
        with self.assertRaises(ValueError):
            video_jobs.new_request("  ")
        with self.assertRaises(ValueError):
            video_jobs.new_request("テーマ", ["http://example.com/a"])

    def test_request_message_asks_for_production_not_publication(self):
        record, call = self.run_video("生成AIの最新ニュース", [], None)
        content = call.call_args.kwargs["json"]["content"]
        self.assertIn("動画制作の承認", content)
        self.assertIn("動画制作を始める", content)
        self.assertIn(f"承認 {record['id']}", content)
        self.assertEqual(call.call_args.kwargs["json"]["allowed_mentions"], {"users": ["222"]})

    def test_pending_topic_writes_no_job(self):
        record, _ = self.run_video("テーマ", [], None)
        self.assertFalse(self.jobs.exists())
        self.assertEqual(record["approval"]["status"], "pending")

    def test_approved_topic_writes_job_and_publishes_nothing(self):
        with patch.object(app, "_deliver") as deliver:
            record, _ = self.run_video("生成AIの最新ニュース", ["https://source.example/a"], "approved")
        deliver.assert_not_called()
        self.assertEqual(record["approval"]["status"], "approved")
        self.assertEqual(record["deliveries"], {})
        job = json.loads((self.jobs / f"{record['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(job["status"], "approved")
        self.assertEqual(job["topic"], "生成AIの最新ニュース")
        self.assertEqual(job["urls"], ["https://source.example/a"])
        self.assertEqual(job["approved_at"], record["approval"]["decided"])

    def test_rejected_topic_writes_no_job(self):
        record, _ = self.run_video("テーマ", [], "rejected")
        self.assertEqual(record["approval"]["status"], "rejected")
        self.assertFalse(self.jobs.exists())

    def test_waiting_topic_body_is_kept_for_the_approval_message(self):
        record, _ = self.run_video("テーマ", ["https://source.example/a"], None)
        saved = json.loads((self.path / "state.json").read_text(encoding="utf-8"))
        saved_record = next(p for p in saved["posts"] if p["id"] == record["id"])
        self.assertIn("参考URL", saved_record["post"]["body"])


if __name__ == "__main__":
    unittest.main()
