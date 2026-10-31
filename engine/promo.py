"""販売中の作品・サービスの多言語プロモ投稿（翻訳した同人作品の海外向け告知、自社商品の紹介など）。
catalog.csv（列: title,url,langs,blurb,tags,adult）→ 言語ごとに投稿文 → output/promo に保存（確認用）→ --publish で X へ。
同じ作品は every_days 日に1回まで（ローテーション）。"""
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from . import llm, state, writer

LANG_NAMES = {"ja": "Japanese", "en": "English", "zh-Hans": "Simplified Chinese", "zh-Hant": "Traditional Chinese", "ko": "Korean"}
PROMPT = """Write one social media post in {lang} promoting this work. Facts below are the only facts you may use.
Title: {title}
What it is: {blurb}
Tags: {tags}
Link: {url}
Rules: natural native {lang}; 1 hook line + 1-2 lines on what it is; 2-3 relevant hashtags; end with the link;
no exaggeration, no invented reviews/rankings/prices; {adult_rule}
Return JSON only: {{"text": "..."}}"""


def load_catalog(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("title") or "").strip() and (r.get("url") or "").strip()]
    for r in rows:
        r["langs"] = [x.strip() for x in (r.get("langs") or "en").replace("/", ",").split(",") if x.strip()]
        r["adult"] = str(r.get("adult", "")).strip().lower() in ("1", "true", "yes", "r18", "18")
    return rows


def compose(work, lang):
    adult_rule = ("this is adult (18+) content: mark it 18+ and keep the text non-explicit (no sexual descriptions)"
                  if work["adult"] else "keep it family-friendly")
    res = llm.ask(PROMPT.format(lang=LANG_NAMES.get(lang, lang), title=work["title"], blurb=work.get("blurb", ""),
                                tags=work.get("tags", ""), url=work["url"], adult_rule=adult_rule), json_mode=True, temperature=0.8)
    text = res.get("text") if isinstance(res, dict) else None
    if not isinstance(text, str) or len(text.strip()) < 10:
        tags = " ".join("#" + t.strip().replace(" ", "") for t in (work.get("tags") or "").split(",") if t.strip())[:80]
        text = f"{'[18+] ' if work['adult'] else ''}{work['title']}\n{work.get('blurb', '')}\n{tags}\n{work['url']}"
    if work["adult"] and "18+" not in text and "R18" not in text.upper():
        text = "[18+] " + text
    return writer.fit_tweet(text.strip())


def run(catalog, st, cfg, limit=5, every_days=7, publish=False, out_dir="output/promo"):
    done = st.setdefault("promo", {})
    cutoff = (datetime.now() - timedelta(days=every_days)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    out = Path(cfg.get("output_dir", "output")) / "promo" / today if out_dir == "output/promo" else Path(out_dir)
    made = []
    for work in load_catalog(catalog):
        for lang in work["langs"]:
            key = f"{work['url']}|{lang}"
            rec = done.get(key, {})
            if rec.get("status") in ("in_progress", "uncertain"):
                continue  # 投稿されたか不明なものは X で確認するまで触らない
            if rec.get("status") == "posted" and rec.get("date", "") > cutoff:
                continue  # 同じ作品は every_days 日に1回まで
            if len(made) >= limit:
                break
            if rec.get("status") == "draft" and rec.get("file") and Path(rec["file"]).exists():
                # 確認済み（手で直したかもしれない）下書きをそのまま使う
                rec = {**rec, **json.loads(Path(rec["file"]).read_text(encoding="utf-8"))}
                rec["text"] = writer.fit_tweet(rec["text"])
            else:
                rec = {"date": today, "title": work["title"], "lang": lang, "text": compose(work, lang), "status": "draft"}
                out.mkdir(parents=True, exist_ok=True)
                f = out / f"{writer.slugify(work['title'])}_{lang}.json"
                f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
                rec["file"] = str(f)
            rec["date"] = today
            if publish:
                from .publishers import x
                rec["status"] = "in_progress"
                done[key] = rec
                state.save(st)  # 投稿前に記録（途中停止で二重投稿しない）
                progress = {}
                try:
                    rec["url"] = x.post_thread([rec["text"]], progress=progress)
                    rec["status"] = "posted"
                except Exception as e:
                    rec["status"] = "uncertain" if progress.get("in_flight") is not None else "failed"
                    rec["error"] = str(e)[:200]
            done[key] = rec
            state.save(st)
            made.append(rec)
            print(f"  [{lang}] {work['title']}: {rec['status']}")
    return made
