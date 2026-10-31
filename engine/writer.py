"""記事・Xスレッド生成 ＋ アフィリエイトリンク差し込み。"""
import re
from datetime import datetime
from pathlib import Path

from . import llm

P = Path(__file__).resolve().parent.parent / "prompts"


def _prompt(name, **kw):
    return (P / f"{name}.md").read_text(encoding="utf-8").format(**kw)


def slugify(s):
    s = re.sub(r"[^\w\s-]", "", s.lower()).strip()
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"[^a-z0-9-]", "", s)[:60].strip("-") or datetime.now().strftime("post-%H%M%S")


def article(item, body, cfg):
    res = llm.ask(_prompt("article", persona=cfg["persona"], niche=cfg["niche"], title=item["title"], url=item["url"],
                          summary=item.get("summary", ""), body=body[:7000], min_chars=cfg.get("min_chars", 2000)),
                  json_mode=True)
    if not isinstance(res, dict) or not res.get("body"):  # キー無し/崩れた応答: 最低限の紹介記事
        res = {"title": item["title"], "slug": slugify(item["title"]), "description": item.get("summary", "")[:120],
               "tags": [item.get("source", "")], "body": f"## 概要\n\n{item.get('summary','')}\n\n## 原文\n\n{body[:1500]}"}
    res.setdefault("title", item["title"])
    res.setdefault("description", "")
    res["tags"] = [t for t in (res.get("tags") or []) if t][:8]
    res["slug"] = slugify(res.get("slug") or res["title"]) or slugify(item["title"])
    res["source_url"] = item["url"]
    res["body"] = inject_affiliates(res["body"], cfg.get("affiliates", [])) + f"\n\n---\n参考: [{item['title']}]({item['url']})\n"
    return res


def pseo(row: dict, cfg):
    """プログラマティックSEO: CSV 1行 × テンプレ → 1記事。"""
    res = llm.ask(_prompt("pseo", persona=cfg["persona"], niche=cfg["niche"], data="\n".join(f"- {k}: {v}" for k, v in row.items()),
                          min_chars=cfg.get("min_chars", 2000)), json_mode=True)
    if not isinstance(res, dict) or not res.get("body"):
        raise RuntimeError("pSEO には GEMINI_API_KEY が必要です（または応答が不正）")
    res.setdefault("description", "")
    res["tags"] = [t for t in (res.get("tags") or []) if t][:8]
    res["slug"] = slugify(res.get("slug") or res["title"])
    res["body"] = inject_affiliates(res["body"], cfg.get("affiliates", []))
    return res


def thread(post, url, cfg):
    res = llm.ask(_prompt("thread", title=post["title"], body=post["body"][:5000], url=url or "", n=cfg.get("thread_len", 4)),
                  json_mode=True)
    tweets = res if isinstance(res, list) else (res or {}).get("tweets") if res else None
    if not tweets:
        tweets = [f"{post['title']}\n\n{post.get('description','')}" + (f"\n{url}" if url else "")]
    return [fit_tweet(str(t)) for t in tweets if str(t).strip()]


URL_RE = re.compile(r"https?://\S+")


def tweet_len(t: str) -> int:
    """X の文字数: URL は一律23、日本語など全角は2、半角は1（上限280）"""
    n = 23 * len(URL_RE.findall(t))
    for ch in URL_RE.sub("", t):
        n += 1 if ord(ch) < 0x1100 or 0xFF61 <= ord(ch) <= 0xFF9F else 2
    return n


def fit_tweet(t: str, limit: int = 280) -> str:
    if tweet_len(t) <= limit:
        return t
    urls = URL_RE.findall(t)
    tail = ("\n" + urls[-1]) if urls else ""
    body = URL_RE.sub("", t).rstrip()
    while body and tweet_len(body + "…" + tail) > limit:
        body = body[:-1]
    return body + "…" + tail


def inject_affiliates(md, affiliates):
    """キーワード初出をリンク化 ＋ 記事末尾におすすめボックス（関連するものだけ）。"""
    used = []
    for a in affiliates:
        kw = a["keyword"]
        # \w は日本語にも当たるので英数字だけで境界判定（「おすすめのXserverは」もリンク化される）
        pat = re.compile(rf"(?<![\[/A-Za-z0-9_]){re.escape(kw)}(?![\]A-Za-z0-9_])")
        if pat.search(md):
            md = pat.sub(f"[{kw}]({a['url']})", md, count=1)
            used.append(a)
    if used:
        md += "\n\n## この記事で紹介したツール・サービス\n\n" + "\n".join(
            f"- [{a.get('label', a['keyword'])}]({a['url']})" for a in used)
        md += "\n\n<small>※本記事にはアフィリエイトリンクを含みます</small>\n"
    return md
