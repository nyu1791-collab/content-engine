"""既出管理＋キュー。data/state.json 1ファイル（GitHub Actions でコミットして永続化）。"""
import json
from datetime import datetime
from pathlib import Path

PATH = Path("data/state.json")


def load():
    if PATH.exists():
        return json.loads(PATH.read_text(encoding="utf-8"))
    return {"seen": {}, "queue": [], "posts": []}


def save(st):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    st["seen"] = dict(list(st["seen"].items())[-5000:])
    st["posts"] = st["posts"][-1000:]
    PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def enqueue(st, items):
    n = 0
    for it in items:
        if it["id"] in st["seen"]:
            continue
        st["seen"][it["id"]] = datetime.now().strftime("%Y-%m-%d")
        st["queue"].append(it)
        n += 1
    st["queue"].sort(key=lambda x: -x.get("score", 0))
    st["queue"] = st["queue"][:200]
    return n
