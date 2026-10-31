import tempfile
import unittest
from tests import network_guard  # noqa: F401
from pathlib import Path
from unittest.mock import patch

import yaml

from engine import writer
from engine.publishers import files


class ThreadTests(unittest.TestCase):
    post = {"title": "記事", "body": "本文", "description": "説明"}

    def test_none_response_keeps_offline_fallback(self):
        with patch.object(writer.llm, "ask", return_value=None):
            self.assertEqual(writer.thread(self.post, "https://example.org/", {}),
                             ["記事\n\n説明\nhttps://example.org/"])

    def test_valid_arrays_are_kept_as_whole_tweets(self):
        for response in ([" 短い文章 ", "二つ目"], {"tweets": [" 短い文章 ", "二つ目"]}):
            with self.subTest(response=response), patch.object(writer.llm, "ask", return_value=response):
                self.assertEqual(writer.thread(self.post, "", {}), ["短い文章", "二つ目"])

    def test_invalid_shape_cannot_be_posted_as_individual_characters(self):
        for response in ("短い文章", {"tweets": "短い文章"}, {}, [], {"tweets": []}, False, 12):
            with self.subTest(response=response), patch.object(writer.llm, "ask", return_value=response):
                with self.assertRaises(ValueError):
                    writer.thread(self.post, "", {})

    def test_nonstring_or_empty_tweets_are_rejected(self):
        for tweets in (["正しい文", None], [{"text": "文章"}], [1], [""], [" \n\t "]):
            with self.subTest(tweets=tweets), patch.object(writer.llm, "ask", return_value={"tweets": tweets}):
                with self.assertRaises(ValueError):
                    writer.thread(self.post, "", {})


class FileTests(unittest.TestCase):
    def test_frontmatter_roundtrips_special_characters_and_newlines(self):
        post = {"title": 'WindowsのC:\\Usersと"引用符"\n次の行', "slug": "windows",
                "description": '説明: 日本語\\new\n複数行: "値"', "tags": ['AI "agent"', "行\n区切り", "C:\\Users"],
                "body": "## 本文\n\n変更しない本文"}
        with tempfile.TemporaryDirectory() as tmp:
            path = files.publish(post, {"output_dir": tmp})
            contents = Path(path).read_text(encoding="utf-8")
        self.assertTrue(contents.startswith("---\n"))
        header, body = contents[4:].split("\n---\n", 1)
        metadata = yaml.safe_load(header)
        for key in ("title", "description", "tags"):
            self.assertEqual(metadata[key], post[key])
        self.assertEqual(body, f'\n{post["body"]}\n')


class AffiliateTests(unittest.TestCase):
    affiliates = [{"keyword": "Xserver", "url": "https://affiliate.example/id", "label": "紹介サービス"}]

    def test_plain_text_gets_related_section_without_rewriting_body(self):
        body = "おすすめのXserverを紹介します。"
        result = writer.inject_affiliates(body, self.affiliates)
        self.assertTrue(result.startswith(body + "\n\n"))
        self.assertIn("[紹介サービス](https://affiliate.example/id)", result)
        self.assertIn("アフィリエイトリンクを含みます", result)

    def test_urls_links_and_code_only_mentions_are_untouched(self):
        cases = ["公式: https://www.Xserver.ne.jp/", "[Xserverの公式](https://example.org/)",
                 "<https://www.Xserver.ne.jp/>", "`Xserver`", "``code `Xserver` block``",
                 "```python\nservice = 'Xserver'\n```", "~~~text\nXserver\n~~~",
                 "    Xserver\n", '<a href="https://example.org/">Xserver</a>',
                 "[Xserver][official]\n\n[official]: https://example.org/"]
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(writer.inject_affiliates(body, self.affiliates), body)

    def test_mixed_markdown_keeps_original_prefix_and_appends_once(self):
        body = "Xserverの解説\n\n公式: https://www.Xserver.ne.jp/\n\n[Xserver](https://example.org/)\n\n```sh\nXserver --help\n```"
        result = writer.inject_affiliates(body, self.affiliates)
        self.assertTrue(result.startswith(body + "\n\n"))
        self.assertEqual(result.count("https://affiliate.example/id"), 1)

    def test_partial_words_and_unrelated_text_do_not_add_advertisement(self):
        for body in ("MyXserverPlus", "別のサービスの解説", ""):
            with self.subTest(body=body):
                self.assertEqual(writer.inject_affiliates(body, self.affiliates), body)


if __name__ == "__main__":
    unittest.main()
