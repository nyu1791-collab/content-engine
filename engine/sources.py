"""ネタ収集: RSS / Googleニュース / Hacker News / GitHub Trending / Reddit。すべてAPIキー不要。
返り値は共通形式 {id, source, title, url, summary, score}。"""
import hashlib
import math
import re
import time
from urllib.parse import quote, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 content-engine"}


def _id(url):
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _clean(html, n=600):
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ")).strip()[:n]


def rss(url, limit=10, **_):
    feed = feedparser.parse(url, agent=UA["User-Agent"])
    return [{"id": _id(e.link), "source": feed.feed.get("title", url), "title": e.title, "url": e.link,
             "summary": _clean(e.get("summary", "")), "score": 0} for e in feed.entries[:limit]]


def google_news(query, limit=10, lang="ja", **_):
    hl = "ja&gl=JP&ceid=JP:ja" if lang == "ja" else "en-US&gl=US&ceid=US:en"
    return rss(f"https://news.google.com/rss/search?q={quote(query)}&hl={hl}", limit)


def hackernews(limit=15, min_points=100, max_age_hours=24, keywords=None, **_):
    """HN上位候補から収集。年齢は投稿時刻基準、0で無制限。語句はタイトル/URL/本文のいずれかに一致。"""
    if limit <= 0:
        return []
    max_age_hours = float(max_age_hours)
    if not math.isfinite(max_age_hours) or max_age_hours < 0:
        raise ValueError("max_age_hours は0以上の有限の時間数で指定してください")
    keywords = [keywords] if isinstance(keywords, str) else (keywords or [])
    # 「AI」が「mail」に一致する等の部分一致を避ける。日本語の前後は許容する。
    patterns = [re.compile(r"(?<![a-z0-9])" + re.escape(word.strip()) + r"(?![a-z0-9])", re.I)
                for word in keywords if isinstance(word, str) and word.strip()]
    now = time.time()
    ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=15).json()[: limit * 3]
    out = []
    for i in ids:
        it = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json", timeout=15).json() or {}
        if max_age_hours:
            try:
                timestamp = it.get("time")
                if isinstance(timestamp, bool):
                    continue
                age = now - float(timestamp)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(age) or not 0 <= age <= max_age_hours * 3600:
                continue
        if patterns:
            content = " ".join(str(it.get(field) or "") for field in ("title", "url", "text"))
            if not any(pattern.search(content) for pattern in patterns):
                continue
        if it.get("score", 0) >= min_points and it.get("url") and it.get("title"):
            out.append({"id": _id(it["url"]), "source": "Hacker News", "title": it["title"], "url": it["url"],
                        "summary": f"HN {it['score']} points, {it.get('descendants', 0)} comments", "score": it["score"]})
        if len(out) >= limit:
            break
    return out


def github_trending(language="", since="daily", limit=15, **_):
    html = requests.get(f"https://github.com/trending/{language}?since={since}", headers=UA, timeout=20).text
    out = []
    for art in BeautifulSoup(html, "html.parser").select("article.Box-row")[:limit]:
        a = art.select_one("h2 a")
        if not a:
            continue
        repo = re.sub(r"\s+", "", a.get_text())
        desc = art.select_one("p")
        today = art.select_one("span.d-inline-block.float-sm-right")
        stars = int(re.sub(r"[^\d]", "", today.get_text()) or 0) if today else 0
        url = f"https://github.com/{repo}"
        out.append({"id": _id(url), "source": "GitHub Trending", "title": repo, "url": url,
                    "summary": (desc.get_text(strip=True) if desc else "") + f" (+{stars} stars today)", "score": stars})
    return out


def reddit(sub, limit=10, **_):
    j = requests.get(f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={limit}", headers=UA, timeout=15).json()
    return [{"id": _id(p["data"]["url"]), "source": f"r/{sub}", "title": p["data"]["title"], "url": p["data"]["url"],
             "summary": p["data"].get("selftext", "")[:600], "score": p["data"]["score"]} for p in j["data"]["children"]]


def firecrawl_search(query, limit=10, tbs="qdr:d", **_):
    """Firecrawl 検索（tbs=qdr:d で過去24時間）。要 FIRECRAWL_API_URL か FIRECRAWL_API_KEY"""
    from . import fc
    if not fc.client():
        raise RuntimeError("Firecrawl 未設定")
    return [{"id": _id(r["url"]), "source": "Firecrawl search", "title": r["title"] or r["url"], "url": r["url"],
             "summary": r["description"], "score": 0} for r in fc.search(query, limit=limit, tbs=tbs)]


def _resolve(url):
    """実在確認＋転送先の最終URL（検索の転送リンク → 記事本体）。存在しなければ None"""
    try:
        r = requests.get(url, headers=UA, timeout=15, allow_redirects=True, stream=True)
        r.close()
        return r.url if r.status_code < 400 else None
    except requests.RequestException:
        return None


def gemini_search(query, limit=8, days=3, lang="ja", **_):
    """Gemini＋Google 検索で最近のニュース・発表を集める（キーだけで使える情報収集）。
    AI が書いた URL は実在するものだけ採用し、足りなければ検索の出典リンクで補う（作り話の URL を通さない）"""
    from . import llm
    prompt = (f"Google 検索で「{query}」に関する過去{days}日以内の新しいニュース・発表・リリースを最大{limit}件集めてください。"
              f"各件: title（元記事の見出し）, url（元記事のURL）, summary（{'日本語で' if lang == 'ja' else 'in English, '}2文）。"
              '確認できたものだけ。JSON のみ: {"items": [{"title": "", "url": "", "summary": ""}]}')
    res, sources = llm.ask_sources(prompt, json_mode=True, temperature=0, task="research")
    items, seen = [], set()
    for it in (res.get("items") if isinstance(res, dict) else []) or []:
        url = _resolve(str(it.get("url") or ""))
        if url and url not in seen:
            seen.add(url)
            items.append({"id": _id(url), "source": "Gemini検索", "title": str(it.get("title") or url)[:200], "url": url,
                          "summary": str(it.get("summary") or "")[:600], "score": 0})
    for src in sources:
        if len(items) >= limit:
            break
        url = _resolve(src["uri"])
        if url and url not in seen:
            seen.add(url)
            items.append({"id": _id(url), "source": "Gemini検索", "title": src["title"] or url, "url": url,
                          "summary": f"「{query}」の検索結果", "score": 0})
    return items[:limit]


TYPES = {"gemini_search": gemini_search, "firecrawl_search": firecrawl_search, "rss": rss, "google_news": google_news, "hackernews": hackernews, "github_trending": github_trending, "reddit": reddit}


def collect(cfg_sources):
    items = []
    for s in cfg_sources:
        s = dict(s)
        kind = s.pop("type")
        try:
            got = TYPES[kind](**s)
            print(f"  {kind}: {len(got)}件")
            items += got
        except Exception as e:
            print(f"  {kind} 失敗: {e}")
    return items


BLOCKED_RE = re.compile(r"Before you continue to Google|Enable JavaScript and cookies|Just a moment\.\.\.|"
                        r"Access Denied|Are you a robot|captcha|ログインしてください|JavaScriptを有効", re.I)


def looks_blocked(text):
    """同意画面・ボット判定・ログイン要求のページは本文ではない"""
    return len(text) < 2000 and bool(BLOCKED_RE.search(text))


def fetch_body(url, n=8000):
    """記事執筆用に元ページ本文を取得。GitHub → README、それ以外 → Firecrawl（JS描画・本文抽出）→ BeautifulSoup。"""
    from . import fc
    try:
        m = re.match(r"https://github.com/([^/]+/[^/]+)/?$", url)
        if m:
            r = requests.get(f"https://raw.githubusercontent.com/{m.group(1)}/HEAD/README.md", timeout=15)
            if r.ok:
                return r.text[:n]
        if fc.client():
            try:
                md, _, _ = fc.scrape(url, main_only=True)
                if len(md) > 200:
                    return md[:n]
            except Exception as e:
                print(f"  firecrawl失敗→ローカル: {e}")
        if urlparse(url).netloc.endswith("news.google.com"):
            return ""  # JS で転送するまとめページ。Firecrawl 無しでは本文を取れない（見出しだけで書かせない）
        r = requests.get(url, headers=UA, timeout=20, stream=True)
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "text/plain" not in ctype:
            r.close()
            return ""  # PDF・画像・動画などは本文として扱わない
        raw = r.raw.read(3_000_000, decode_content=True)  # 巨大ページの全読込を防ぐ
        r.close()
        text = raw.decode(r.encoding or requests.utils.get_encoding_from_headers(r.headers) or "utf-8", errors="replace")
        soup = BeautifulSoup(text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header", "aside"]):
            t.decompose()
        main = soup.find("article") or soup.find("main") or soup.body or soup
        body = re.sub(r"\n\s*\n+", "\n", main.get_text("\n")).strip()
        return "" if looks_blocked(body) else body[:n]
    except Exception:
        return ""
