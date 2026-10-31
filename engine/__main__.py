"""使い方: python -m engine <command>
  collect              ネタ収集 → キューへ（既出は除外）
  write  [-n 2]        キュー上位を記事化して公開（config の publishers へ）
  run    [-n 2]        collect + write（毎日これ1本）
  pseo data/pseo.csv   CSVの各行から記事を量産（プログラマティックSEO）
  note-login           note 用ログイン状態を保存
  status               キュー・投稿数"""
import argparse
import csv
import os
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from . import sources, state, writer  # noqa: E402
from .publishers import files  # noqa: E402


def cfg():
    return yaml.safe_load(Path(os.getenv("CONFIG", "config.yaml")).read_text(encoding="utf-8"))


def publish(post, c, st):
    links = {"file": files.publish(post, c)}
    pubs = c.get("publishers", [])
    for name in pubs:
        try:
            if name == "wordpress":
                from .publishers import wordpress
                links["wordpress"] = wordpress.publish(post, c)
            elif name == "note":
                from .publishers import note
                links["note"] = note.publish(post, c)
        except Exception as e:
            print(f"  {name} 失敗: {e}")
    if "x" in pubs:
        try:
            from .publishers import x
            url = links.get("wordpress") or post.get("source_url")
            tweets = writer.thread(post, url, c)
            links["x"] = x.post_thread(tweets)
        except Exception as e:
            print(f"  x 失敗: {e}")
    st["posts"].append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "title": post["title"], **links})
    print(f"  ✓ {post['title']}  {links}")


def do_collect(c, st):
    n = state.enqueue(st, sources.collect(c["sources"]))
    print(f"新規 {n}件 / キュー {len(st['queue'])}件")


def do_write(c, st, n):
    for _ in range(min(n, len(st["queue"]))):
        item = st["queue"].pop(0)
        print(f"▶ {item['title']}")
        try:
            post = writer.article(item, sources.fetch_body(item["url"]) or item.get("summary", ""), c)
            publish(post, c, st)
        except Exception as e:
            print(f"  ✗ {e}")
        state.save(st)
        time.sleep(c.get("interval_sec", 5))


def main():
    ap = argparse.ArgumentParser(prog="engine", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("collect")
    for name in ("write", "run"):
        sp.add_parser(name).add_argument("-n", type=int, default=None)
    p = sp.add_parser("pseo"); p.add_argument("csv"); p.add_argument("--limit", type=int, default=10)
    sp.add_parser("note-login")
    sp.add_parser("status")
    a = ap.parse_args()
    c, st = cfg(), state.load()

    if a.cmd in ("collect", "run"):
        do_collect(c, st); state.save(st)
    if a.cmd in ("write", "run"):
        do_write(c, st, a.n or c.get("posts_per_run", 2))
    if a.cmd == "pseo":
        done = {p.get("pseo_key") for p in st["posts"]}
        with open(a.csv, encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f) if "|".join(r.values()) not in done][: a.limit]
        for r in rows:
            print(f"▶ {r}")
            try:
                post = writer.pseo(r, c)
                publish(post, c, st)
                st["posts"][-1]["pseo_key"] = "|".join(r.values())
            except Exception as e:
                print(f"  ✗ {e}")
            state.save(st)
    if a.cmd == "note-login":
        from .publishers import note
        note.login()
    if a.cmd == "status":
        print(f"キュー {len(st['queue'])} / 投稿済み {len(st['posts'])}")
        for p in st["posts"][-5:]:
            print(f"  {p['date']} {p['title']}")


if __name__ == "__main__":
    main()
