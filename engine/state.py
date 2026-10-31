"""既出管理＋キュー。data/state.json 1ファイル（GitHub Actions でコミットして永続化）。"""
import json
from datetime import datetime, timedelta
from pathlib import Path

PATH = Path("data/state.json")


def load():
    if PATH.exists():
        st = json.loads(PATH.read_text(encoding="utf-8"))
    else:
        st = {"seen": {}, "queue": [], "posts": []}
    _remember_pseo(st)
    return st


def _remember_pseo(st):
    # 投稿履歴の表示件数を減らしても、生成済みCSV行は忘れない。
    done = st.setdefault("pseo_done", {})
    for post in st["posts"]:
        if post.get("pseo_key"):
            done[post["pseo_key"]] = post.get("id", post.get("title", ""))


def needs_attention(post):
    return (post.get("draft_status") in ("pending", "failed") or
            any(d.get("status") != "succeeded" for d in post.get("deliveries", {}).values()))


def save(st):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    _remember_pseo(st)
    st["seen"] = dict(list(st["seen"].items())[-5000:])
    recent = {id(p) for p in st["posts"][-1000:]}
    st["posts"] = [p for p in st["posts"] if id(p) in recent or needs_attention(p)]
    pending = PATH.with_suffix(".json.tmp")
    pending.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    pending.replace(PATH)


def enqueue(st, items):
    n = 0
    for it in items:
        if it["id"] in st["seen"]:
            continue
        st["seen"][it["id"]] = datetime.now().strftime("%Y-%m-%d")
        it["added"] = datetime.now().strftime("%Y-%m-%d")
        st["queue"].append(it)
        n += 1
    # 古いネタ（7日超）は捨てる。ソースごとに上位だけ残す
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    st["queue"] = [q for q in st["queue"] if q.get("added", cutoff) >= cutoff]
    st["queue"].sort(key=lambda x: -x.get("score", 0))
    per = {}
    st["queue"] = [q for q in st["queue"] if per.setdefault(q["source"], []).append(1) or len(per[q["source"]]) <= 40]
    return n


def next_item(st):
    """ソースを順番に回して取り出す（HNやGitHubのスコアが大きくてもRSS/ニュースが埋もれない）"""
    if not st["queue"]:
        return None
    order = st.setdefault("source_order", [])
    srcs = list(dict.fromkeys(q["source"] for q in st["queue"]))
    for s in srcs:
        if s not in order:
            order.append(s)
    pick = next((s for s in order if s in srcs), srcs[0])
    order.remove(pick)
    order.append(pick)  # 使ったソースは最後尾へ
    i = next(i for i, q in enumerate(st["queue"]) if q["source"] == pick)
    return st["queue"].pop(i)
