import json
import sys
import tempfile
import types
import unittest
from tests import network_guard  # noqa: F401
from pathlib import Path
from unittest.mock import Mock, patch

from engine import __main__ as app, state
from engine.publishers import files, wordpress, x


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.patch = patch.object(state, "PATH", self.path / "state.json")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.thread = patch.object(app.writer, "thread", return_value=["日本語の確認用ポスト"])
        self.thread_mock = self.thread.start()
        self.addCleanup(self.thread.stop)
        self.st = {"seen": {}, "queue": [], "posts": []}
        self.cfg = {"output_dir": str(self.path / "output"), "publishers": [], "wp_status": "draft"}
        self.post = {"title": "記事", "slug": "test", "body": "本文", "tags": [],
                     "source_url": "https://source.example/article"}

    def test_file_only_saves_reviewable_tweets(self):
        record = app.publish(self.post, self.cfg, self.st)
        draft = json.loads(Path(record["draft_file"]).read_text(encoding="utf-8"))
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["tweets"], ["日本語の確認用ポスト"])
        self.assertEqual(record["deliveries"]["file"]["status"], "succeeded")
        # 配信が全部済んだ記録は本文を state から外す（本文は output/ の記事ファイルにある）
        saved = state.load()["posts"][0]["post"]
        self.assertEqual(saved, {k: self.post[k] for k in ("title", "slug", "source_url")})
        self.assertIn("本文", Path(record["deliveries"]["file"]["url"]).read_text(encoding="utf-8"))

    def test_retry_only_failed_destination_and_keeps_original_draft_mode(self):
        self.cfg["publishers"] = ["wordpress"]
        with patch.object(wordpress, "publish", side_effect=RuntimeError("503")):
            record = app.publish(self.post, self.cfg, self.st, pseo_key="row-1")
        self.assertEqual(record["deliveries"]["wordpress"]["status"], "failed")
        self.assertEqual(state.load()["pseo_done"]["row-1"], record["id"])
        self.st = state.load()  # 再起動後でも、成功済みの公開先を再送しない。
        with patch.object(files, "publish") as file_publish, patch.object(wordpress, "publish", return_value="https://blog.example/?p=123") as wp:
            app.do_retry({**self.cfg, "wp_status": "publish"}, self.st)
            self.assertFalse(file_publish.called)
            self.assertEqual(wp.call_args.args[1]["wp_status"], "draft")
            app.do_retry(self.cfg, self.st)
            self.assertEqual(wp.call_count, 1)
        self.assertEqual(len(self.st["posts"]), 1)

    def test_wordpress_draft_link_is_not_shared_on_x(self):
        self.cfg["publishers"] = ["wordpress", "x"]
        with patch.object(wordpress, "publish", return_value="https://blog.example/?p=123"), patch.object(x, "post_thread", return_value="https://x.com/i/status/1"):
            app.publish(self.post, self.cfg, self.st)
        self.assertEqual(self.thread_mock.call_args.args[1], self.post["source_url"])

    def test_wordpress_public_link_is_shared_on_x(self):
        self.cfg.update(publishers=["wordpress", "x"], wp_status="publish")
        with patch.object(wordpress, "publish", return_value="https://blog.example/test"), patch.object(x, "post_thread", return_value="https://x.com/i/status/1"):
            app.publish(self.post, self.cfg, self.st)
        self.assertEqual(self.thread_mock.call_args.args[1], "https://blog.example/test")

    def test_partial_x_thread_is_preserved_and_not_automatically_resent(self):
        self.cfg["publishers"] = ["x"]

        def partial(tweets, progress, on_progress):
            progress.update(ids=["first-post-id"], in_flight=1)
            on_progress()
            raise TimeoutError("response lost")

        with patch.object(x, "post_thread", side_effect=partial) as send:
            record = app.publish(self.post, self.cfg, self.st)
            app.do_retry(self.cfg, self.st)
            self.assertEqual(send.call_count, 1)
        saved = state.load()["posts"][0]["deliveries"]["x"]
        self.assertEqual(saved["status"], "uncertain")
        self.assertEqual(saved["progress"]["ids"], ["first-post-id"])

    def test_interrupted_destination_is_not_automatically_resent(self):
        self.cfg["publishers"] = ["wordpress"]
        with patch.object(wordpress, "publish", return_value="https://blog.example/test"):
            record = app.publish(self.post, self.cfg, self.st)
        record["deliveries"]["wordpress"]["status"] = "in_progress"
        with patch.object(wordpress, "publish") as wp:
            app.do_retry(self.cfg, self.st)
            self.assertFalse(wp.called)

    def test_draft_failure_can_be_retried_without_republishing_article(self):
        self.cfg["publishers"] = ["wordpress"]
        self.thread_mock.side_effect = RuntimeError("temporary generator failure")
        with patch.object(wordpress, "publish", return_value="https://blog.example/test") as wp:
            record = app.publish(self.post, self.cfg, self.st)
            self.assertEqual(record["draft_status"], "failed")
            self.thread_mock.side_effect = None
            app.do_retry(self.cfg, self.st)
            self.assertEqual(wp.call_count, 1)
        self.assertEqual(record["draft_status"], "succeeded")

    def test_interrupted_draft_generation_can_resume_after_restart(self):
        self.thread_mock.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            app.publish(self.post, self.cfg, self.st)
        loaded = state.load()
        self.assertEqual(loaded["posts"][0]["draft_status"], "pending")
        self.thread_mock.side_effect = None
        self.thread_mock.reset_mock()
        app.do_retry(self.cfg, loaded)
        self.thread_mock.assert_called_once()
        self.assertEqual(loaded["posts"][0]["draft_status"], "succeeded")

    def test_wordpress_success_without_usable_response_is_not_resent(self):
        self.cfg["publishers"] = ["wordpress"]
        response = Mock(status_code=201)
        response.json.return_value = {"id": 123}  # 保存成功でもlinkの取得に失敗し得る。
        with patch.dict("os.environ", {"WP_URL": "https://blog.example", "WP_USER": "user", "WP_APP_PASSWORD": "test"}), patch.object(wordpress.requests, "post", return_value=response) as send:
            record = app.publish(self.post, self.cfg, self.st)
            app.do_retry(self.cfg, state.load())
            self.assertEqual(send.call_count, 1)
        self.assertEqual(record["deliveries"]["wordpress"]["status"], "uncertain")

    def test_x_records_each_confirmed_id_before_next_send(self):
        client = Mock()
        client.create_tweet.side_effect = [types.SimpleNamespace(data={"id": "first-id"}), TimeoutError("response lost")]
        tweepy = types.SimpleNamespace(Client=Mock(return_value=client))
        progress, snapshots = {}, []
        credentials = {key: "test" for key in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")}
        with patch.dict(sys.modules, {"tweepy": tweepy}), patch.dict("os.environ", credentials):
            with self.assertRaises(TimeoutError):
                x.post_thread(["one", "two"], progress, lambda: snapshots.append(json.loads(json.dumps(progress))))
            self.assertEqual(progress, {"ids": ["first-id"], "in_flight": 1})
            self.assertIn({"ids": ["first-id"]}, snapshots)
            with self.assertRaises(RuntimeError):
                x.post_thread(["one", "two"], progress)
        self.assertEqual(client.create_tweet.call_count, 2)

    def test_pseo_resume_history_survives_trimming(self):
        self.st["posts"] = [{"pseo_key": str(i)} for i in range(1001)]
        self.st["posts"][0].update(deliveries={"wordpress": {"status": "failed"}})
        state.save(self.st)
        loaded = state.load()
        self.assertIn("0", loaded["pseo_done"])
        self.assertIn("1000", loaded["pseo_done"])
        self.assertTrue(any(p["pseo_key"] == "0" for p in loaded["posts"]))

    def test_pseo_key_is_unambiguous_and_ignores_column_order(self):
        self.assertNotEqual(app._pseo_key({"a": "x|y", "b": "z"}), app._pseo_key({"a": "x", "b": "y|z"}))
        self.assertEqual(app._pseo_key({"a": "x", "b": "y"}), app._pseo_key({"b": "y", "a": "x"}))


if __name__ == "__main__":
    unittest.main()
