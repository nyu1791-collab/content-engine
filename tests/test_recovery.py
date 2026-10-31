import contextlib
import io
import os
from pathlib import Path
import tempfile
import types
import unittest
from tests import network_guard
from unittest.mock import Mock, patch

import requests
import tweepy

from engine import __main__ as app, state, writer
from engine.publishers import wordpress


class RecoveryFixture:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.patch = patch.object(state, "PATH", self.root / "state.json")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.st = {"seen": {}, "queue": [], "posts": []}
        self.cfg = {"publishers": [], "output_dir": str(self.root / "output"), "interval_sec": 0}
        self.post = {"title": "記事", "slug": "article", "body": "本文", "tags": [],
                     "source_url": "https://source.invalid/article"}
        self.item = {"id": "source-1", "source": "HN", "title": "記事", "url": self.post["source_url"]}
        self.thread = patch.object(app.writer, "thread", return_value=["下書きの本文"])
        self.thread.start()
        self.addCleanup(self.thread.stop)


class RecoveryTests(RecoveryFixture, unittest.TestCase):
    def test_state_error_after_remote_success_does_not_requeue_source(self):
        self.st["queue"] = [self.item]
        self.cfg["publishers"] = ["wordpress"]
        save, failed = state.save, False

        def fail_once_after_wordpress_success(st):
            nonlocal failed
            if not failed and any(p["deliveries"].get("wordpress", {}).get("status") == "succeeded" for p in st["posts"]):
                failed = True
                raise OSError("temporary state write failure")
            save(st)

        with patch.object(state, "save", side_effect=fail_once_after_wordpress_success), patch.object(app.writer, "article", return_value=self.post), patch.object(app.sources, "fetch_body", return_value="source"), patch.object(wordpress, "publish", return_value="https://blog.invalid/article") as publish:
            app.do_write(self.cfg, self.st, 1)
            self.st = state.load()
            self.assertEqual(self.st["queue"], [])
            self.assertEqual(self.st["posts"][0]["source_id"], "source-1")
            app.do_write(self.cfg, self.st, 1)
            app.do_retry(self.cfg, self.st)
        self.assertEqual(publish.call_count, 1)
        self.assertEqual(len(self.st["posts"]), 1)

    def test_initial_record_save_failure_recovers_pending_record_without_regeneration(self):
        self.st["queue"] = [self.item]
        save, failed = state.save, False

        def fail_first_save(st):
            nonlocal failed
            if not failed:
                failed = True
                raise OSError("temporary state write failure")
            save(st)

        with patch.object(state, "save", side_effect=fail_first_save), patch.object(app.writer, "article", return_value=self.post) as generate, patch.object(app.sources, "fetch_body", return_value="source"):
            app.do_write(self.cfg, self.st, 1)
            loaded = state.load()
            self.assertEqual(loaded["queue"], [])
            self.assertEqual(loaded["posts"][0]["deliveries"]["file"]["status"], "pending")
            app.do_retry(self.cfg, loaded)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(len(loaded["posts"]), 1)
        self.assertEqual(loaded["posts"][0]["deliveries"]["file"]["status"], "succeeded")

    def test_duplicate_queued_source_uses_existing_record(self):
        app.publish(self.post, self.cfg, self.st, source_id="source-1")
        self.st["queue"] = [self.item]
        with patch.object(app.writer, "article") as generate:
            app.do_write(self.cfg, self.st, 1)
        generate.assert_not_called()
        self.assertEqual(len(self.st["posts"]), 1)

    def test_pseo_missing_and_extra_columns_do_not_block_valid_rows(self):
        path = self.root / "keywords.csv"
        path.write_text("地域,用途\n渋谷\n余剰,列,あり\n新宿,売上\n新宿,売上\n池袋,請求\n", encoding="utf-8")
        with patch("sys.argv", ["engine", "pseo", str(path), "--limit", "2"]), patch.object(app, "cfg", return_value=self.cfg), patch.object(app.writer, "pseo", return_value=self.post) as generate:
            app.main()
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(generate.call_args_list[0].args[0], {"地域": "新宿", "用途": "売上"})
            self.assertEqual(generate.call_args_list[1].args[0], {"地域": "池袋", "用途": "請求"})
            app.main()
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(len(state.load()["posts"]), 2)

    def test_pseo_rejects_ambiguous_headers(self):
        path = self.root / "keywords.csv"
        for header in ("地域,地域", "地域,", ""):
            path.write_text(header + "\n", encoding="utf-8")
            with self.subTest(header=header), self.assertRaises(ValueError):
                app._pseo_rows(path, set(), 1)

    def test_invalid_tweet_response_is_held_before_any_x_submission(self):
        self.thread.stop()
        self.cfg["publishers"] = ["x"]
        with patch.object(writer.llm, "ask", return_value={"tweets": "一文字ずつ投稿しない"}), patch("engine.publishers.x.post_thread") as submit:
            record = app.publish(self.post, self.cfg, self.st)
        submit.assert_not_called()
        self.assertEqual(record["draft_status"], "failed")
        self.assertEqual(record["deliveries"]["x"]["status"], "pending")

    def test_network_guard_is_active_before_the_suite(self):
        with self.assertRaises(network_guard.LiveNetworkBlocked):
            requests.Session().request("GET", "https://should-not-connect.invalid/")

    def test_zero_count_commands_do_not_read_state_or_contact_sources(self):
        commands = (["run", "-n", "0"], ["write", "-n", "0"], ["retry", "-n", "0"],
                    ["pseo", "does-not-exist.csv", "--limit", "0"])
        for command in commands:
            with self.subTest(command=command), patch("sys.argv", ["engine", *command]), patch.object(app, "cfg") as cfg, patch.object(state, "load") as load:
                app.main()
                cfg.assert_not_called()
                load.assert_not_called()

    def test_configured_zero_posts_skips_collection(self):
        with patch("sys.argv", ["engine", "run"]), patch.object(app, "cfg", return_value={"posts_per_run": 0}), patch.object(app.sources, "collect") as collect, patch.object(state, "load") as load:
            app.main()
        collect.assert_not_called()
        load.assert_not_called()

    def test_negative_counts_are_cli_errors(self):
        commands = (["run", "-n", "-1"], ["write", "-n", "-1"], ["retry", "-n", "-1"],
                    ["pseo", "keywords.csv", "--limit", "-1"])
        for command in commands:
            with self.subTest(command=command), patch("sys.argv", ["engine", *command]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                app.main()
            self.assertEqual(error.exception.code, 2)

    def test_invalid_configured_counts_are_cli_errors(self):
        for value in (-1, 1.5, True):
            with self.subTest(value=value), patch("sys.argv", ["engine", "run"]), patch.object(app, "cfg", return_value={"posts_per_run": value}), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                app.main()
            self.assertEqual(error.exception.code, 2)


class XRejectionTests(RecoveryFixture, unittest.TestCase):
    @staticmethod
    def rejection(status):
        response = requests.Response()
        response.status_code = status
        response._content = b'{"errors":[{"message":"fixture rejection","code":88}]}'
        return tweepy.HTTPException(response)

    def setUp(self):
        super().setUp()
        self.cfg["publishers"] = ["x"]
        credentials = {name: "test" for name in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")}
        patcher = patch.dict(os.environ, credentials)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_definitive_initial_rejection_can_retry(self):
        for status in (400, 401, 403, 429):
            client = Mock()
            client.create_tweet.side_effect = [self.rejection(status), types.SimpleNamespace(data={"id": "confirmed-id"})]
            with self.subTest(status=status), patch.object(tweepy, "Client", return_value=client):
                record = app.publish(self.post, self.cfg, self.st)
                self.assertEqual(record["deliveries"]["x"]["status"], "failed")
                self.assertNotIn("in_flight", record["deliveries"]["x"]["progress"])
                app.do_retry(self.cfg, self.st, record["id"])
            self.assertEqual(client.create_tweet.call_count, 2)
            self.assertEqual(record["deliveries"]["x"]["status"], "succeeded")

    def test_request_timeout_response_is_not_resent(self):
        client = Mock()
        client.create_tweet.side_effect = self.rejection(408)
        with patch.object(tweepy, "Client", return_value=client):
            record = app.publish(self.post, self.cfg, self.st)
            app.do_retry(self.cfg, self.st, record["id"])
        self.assertEqual(client.create_tweet.call_count, 1)
        self.assertEqual(record["deliveries"]["x"]["status"], "uncertain")

    def test_rejection_after_partial_thread_is_not_resent(self):
        client = Mock()
        client.create_tweet.side_effect = [types.SimpleNamespace(data={"id": "first-id"}), self.rejection(429)]
        with patch.object(tweepy, "Client", return_value=client), patch.object(app.writer, "thread", return_value=["first", "second"]):
            record = app.publish(self.post, self.cfg, self.st)
            app.do_retry(self.cfg, self.st, record["id"])
        self.assertEqual(client.create_tweet.call_count, 2)
        self.assertEqual(record["deliveries"]["x"]["status"], "uncertain")
        self.assertEqual(record["deliveries"]["x"]["progress"]["ids"], ["first-id"])


if __name__ == "__main__":
    unittest.main()


class StateSizeTests(RecoveryFixture, unittest.TestCase):
    def test_completed_records_drop_body_but_retryable_keep_it(self):
        record = app.publish(self.post, self.cfg, self.st, source_id="done-1")
        self.assertEqual(record["deliveries"]["file"]["status"], "succeeded")
        failed = {"id": "f1", "date": "", "title": "x", "post": dict(self.post),
                  "draft_status": "succeeded", "deliveries": {"wordpress": {"status": "failed"}}}
        self.st["posts"].append(failed)
        state.save(self.st)
        saved = state.load()
        done, retry = saved["posts"][0], saved["posts"][1]
        self.assertNotIn("body", done["post"])
        self.assertEqual(done["post"]["source_url"], self.post["source_url"])
        self.assertEqual(retry["post"]["body"], "本文")
