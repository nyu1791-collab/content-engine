import unittest
from tests import network_guard  # noqa: F401
from unittest.mock import patch

from engine import writer

CFG = {"persona": "案内人", "niche": "通販", "min_chars": 1500}
ROW = {"product_name": "テスト商品", "shop": "Amazon", "price_yen": "1980", "checked_date": "2026-11-02",
       "official_url": "https://shop.example/item", "affiliate_url": "https://affiliate.example/link",
       "features": "軽い; 折りたたみ", "notes": "送料はページで確認"}


class AffiliatePromptTests(unittest.TestCase):
    def render(self, prompt, row=ROW):
        with patch.object(writer.llm, "ask", return_value={"title": "テスト記事", "body": "本文"}) as ask:
            writer.pseo(row, CFG, prompt=prompt)
        return ask.call_args.args[0]

    def test_product_prompt_discloses_ads_and_uses_only_the_row(self):
        text = self.render("affiliate_product")
        self.assertIn("本記事はアフィリエイト広告を含みます", text)
        self.assertIn("- product_name: テスト商品", text)
        self.assertIn("https://affiliate.example/link", text)
        self.assertIn("体験談", text)

    def test_adult_prompt_has_age_notice_and_no_sexual_description(self):
        text = self.render("affiliate_adult")
        self.assertIn("18歳未満の方は閲覧できません", text)
        self.assertIn("性的な描写", text)
        self.assertIn("- product_name: テスト商品", text)

    def test_product_prompt_without_affiliate_url_renders(self):
        row = {**ROW, "affiliate_url": ""}
        text = self.render("affiliate_product", row)
        self.assertIn("- affiliate_url: \n", text)


if __name__ == "__main__":
    unittest.main()
