import json
import tempfile
import unittest
from pathlib import Path
from tests import network_guard  # noqa: F401
from unittest.mock import Mock, patch

from scripts import dispatch_video_jobs as dispatcher

JOB = {"id": "0123456789ab", "status": "approved", "topic": "生成AIの最新ニュース",
       "urls": ["https://source.example/a", "https://source.example/b"], "created": "2026-11-03 10:00"}


def write(directory, name, job):
    path = Path(directory) / name
    path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    return path


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_only_approved_jobs_are_dispatched(self):
        write(self.dir, "a.json", JOB)
        write(self.dir, "b.json", {**JOB, "id": "fedcba987654", "status": "dispatched"})
        self.assertEqual([job["id"] for _, job in dispatcher.pending_jobs(self.dir)], ["0123456789ab"])

    def test_dispatch_sends_job_inputs_to_voicebox_workflow(self):
        response = Mock(status_code=204)
        with patch.object(dispatcher.requests, "post", return_value=response) as post:
            dispatcher.dispatch(JOB, "owner/voicebox", "tok")
        url = post.call_args.args[0]
        self.assertEqual(url, "https://api.github.com/repos/owner/voicebox/actions/workflows/video-job.yml/dispatches")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["ref"], "main")
        self.assertEqual(body["inputs"]["job_id"], "0123456789ab")
        self.assertEqual(body["inputs"]["topic"], "生成AIの最新ニュース")
        self.assertEqual(body["inputs"]["urls"], "https://source.example/a\nhttps://source.example/b")

    def test_success_marks_job_dispatched_and_is_not_sent_again(self):
        path = write(self.dir, "0123456789ab.json", JOB)
        with patch.object(dispatcher.requests, "post", return_value=Mock(status_code=204)) as post, \
             patch.dict("os.environ", {"VIDEO_JOB_DIR": str(self.dir), "VOICEBOX_REPO": "owner/voicebox",
                                       "VOICEBOX_DISPATCH_TOKEN": "tok"}):
            self.assertEqual(dispatcher.main(), 0)
            self.assertEqual(dispatcher.main(), 0)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], "dispatched")

    def test_failure_is_recorded_and_not_retried_automatically(self):
        path = write(self.dir, "0123456789ab.json", JOB)
        with patch.object(dispatcher.requests, "post", return_value=Mock(status_code=404)) as post, \
             patch.dict("os.environ", {"VIDEO_JOB_DIR": str(self.dir), "VOICEBOX_REPO": "owner/voicebox",
                                       "VOICEBOX_DISPATCH_TOKEN": "tok"}):
            self.assertEqual(dispatcher.main(), 1)
            self.assertEqual(dispatcher.main(), 0)
        self.assertEqual(post.call_count, 1)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "dispatch_failed")
        self.assertIn("404", saved["error"])


if __name__ == "__main__":
    unittest.main()
