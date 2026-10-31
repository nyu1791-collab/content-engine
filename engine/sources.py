"""ネタ収集: RSS / Googleニュース / Hacker News / GitHub Trending / Reddit。すべてAPIキー不要。
返り値は共通形式 {id, source, title, url, summary, score}。"""
import hashlib
import re
from urllib.parse import quote

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


def hackernews(limit=15, min_points=100, **_):
    ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=15).json()[: limit * 3]
    out = []
    for i in ids:
        it = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json", timeout=15).json() or {}
        if it.get("score", 0) >= min_points and it.get("url"):
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


TYPES = {"rss": rss, "google_news": google_news, "hackernews": hackernews, "github_trending": github_trending, "reddit": reddit}


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


def fetch_body(url, n=8000):
    """記事執筆用に元ページ本文を取得（GitHubならREADME）。"""
    try:
        m = re.match(r"https://github.com/([^/]+/[^/]+)/?$", url)
        if m:
            r = requests.get(f"https://raw.githubusercontent.com/{m.group(1)}/HEAD/README.md", timeout=15)
            if r.ok:
                return r.text[:n]
        r = requests.get(url, headers=UA, timeout=20)
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header", "aside"]):
            t.decompose()
        main = soup.find("article") or soup.find("main") or soup.body or soup
        return re.sub(r"\n\s*\n+", "\n", main.get_text("\n")).strip()[:n]
    except Exception:
        return ""
