"""HNの時刻と分野絞り込み。公開APIへ通信せず固定時刻・HTTP応答で検証する。"""
import unittest
from tests import network_guard  # noqa: F401
from unittest.mock import Mock, patch

from engine import sources


NOW = 1_800_000_000


def story(index, **values):
    return {"title": "AI model update", "url": f"https://example.org/news/{index}",
            "score": 200, "time": NOW - 3600, **values}


class HackerNewsTests(unittest.TestCase):
    def collect(self, items, **kwargs):
        def get(url, timeout):
            if url.endswith("/topstories.json"):
                return Mock(json=lambda: list(range(len(items))))
            index = int(url.rsplit("/", 1)[1].removesuffix(".json"))
            return Mock(json=lambda: items[index])

        with patch.object(sources.requests, "get", side_effect=get), patch.object(sources.time, "time", return_value=NOW):
            return sources.hackernews(limit=20, **kwargs)

    def test_default_age_accepts_last_24_hours_including_boundary(self):
        items = [story(0, time=NOW), story(1, time=NOW - 86400), story(2, time=NOW - 86401)]
        self.assertEqual([x["url"] for x in self.collect(items)], [items[0]["url"], items[1]["url"]])

    def test_invalid_missing_and_future_timestamps_are_excluded(self):
        items = [story(i, time=value) for i, value in enumerate((None, "invalid", float("nan"), float("inf"), True, NOW + 1))]
        missing = story(99)
        del missing["time"]
        self.assertEqual(self.collect(items + [missing]), [])

    def test_zero_age_disables_time_filter_including_missing_time(self):
        missing = story(0)
        del missing["time"]
        items = [missing, story(1, time=NOW - 86400 * 7)]
        self.assertEqual(len(self.collect(items, max_age_hours=0)), 2)

    def test_custom_age_is_honored(self):
        items = [story(0, time=NOW - 7200), story(1, time=NOW - 7201)]
        self.assertEqual([x["url"] for x in self.collect(items, max_age_hours=2)], [items[0]["url"]])

    def test_empty_keywords_keep_other_topics(self):
        self.assertEqual(len(self.collect([story(0, title="Database update")], keywords=[])), 1)

    def test_keywords_match_title_url_or_text_without_matching_inside_words(self):
        items = [story(0, title="New ai model"),
                 story(1, title="New product", url="https://openai.com/release"),
                 story(2, title="Research paper", text="An LLM for businesses"),
                 story(3, title="Mail server update")]
        result = self.collect(items, keywords=["AI", "OpenAI", "LLM"])
        self.assertEqual([x["url"] for x in result], [item["url"] for item in items[:3]])

    def test_string_keyword_is_one_phrase(self):
        result = self.collect([story(0, title="Machine learning for invoices"), story(1, title="Learning databases")],
                              keywords="machine learning")
        self.assertEqual(len(result), 1)

    def test_existing_score_and_url_requirements_still_apply(self):
        items = [story(0, score=99), story(1, url=""), story(2)]
        self.assertEqual([x["url"] for x in self.collect(items)], [items[2]["url"]])

    def test_negative_or_nonfinite_age_is_configuration_error(self):
        for value in (-1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.collect([], max_age_hours=value)

    def test_zero_limit_does_not_fetch(self):
        with patch.object(sources.requests, "get") as get:
            self.assertEqual(sources.hackernews(limit=0), [])
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
