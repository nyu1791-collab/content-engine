"""使い方: python -m engine <command>
  collect              ネタ収集 → キューへ（既出は除外）
  write  [-n 2]        キュー上位を記事化して公開（config の publishers へ）
  run    [-n 2]        collect + write（毎日これ1本）
  pseo data/pseo.csv   CSVの各行から記事を量産（プログラマティックSEO）
  login note|x         note / X のログイン状態を保存（browser-use 投稿用・一度だけ）
  status               キュー・投稿数"""
import argparse
import csv
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from . import sources, state, writer  # noqa: E402
from .publishers import files, UncertainDelivery  # noqa: E402


def cfg():
    return yaml.safe_load(Path(os.getenv("CONFIG", "config.yaml")).read_text(encoding="utf-8"))


def nonnegative_int(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise argparse.ArgumentTypeError("0以上の整数を指定してください")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("0以上の整数を指定してください") from None
    if number < 0:
        raise argparse.ArgumentTypeError("0以上の整数を指定してください")
    return number


def _existing_record(st, source_id=None, pseo_key=None):
    return next((record for record in st["posts"]
                 if ((source_id is not None and record.get("source_id") == source_id) or
                     (pseo_key is not None and record.get("pseo_key") == pseo_key))), None)


def _retryable(record):
    return (record.get("draft_status") in ("pending", "failed") or
            any(d.get("status") in ("pending", "failed") for d in record.get("deliveries", {}).values()))


def _public_url(record):
    for name in ("wordpress", "note"):
        delivery = record["deliveries"].get(name, {})
        if delivery.get("status") == "succeeded" and delivery.get("public"):
            return delivery["url"]
    return record["post"].get("source_url", "")


def _deliver(record, c, st):
    post = record["post"]
    deliveries = record["deliveries"]
    # 投稿時に決めた公開/下書き設定は、後日の再試行でも引き継ぐ。
    delivery_cfg = {**c, **record.get("publish_config", {})}
    for name, delivery in deliveries.items():
        if name in ("x", "x_browser") or delivery["status"] not in ("pending", "failed"):
            continue
        delivery.update(status="in_progress")
        delivery.pop("error", None)
        state.save(st)  # 送信前に記録。途中停止後の無条件な二重送信を避ける。
        browser_started = False
        try:
            if name == "file":
                url = files.publish(post, delivery_cfg)
            elif name == "wordpress":
                from .publishers import wordpress
                url = wordpress.publish(post, delivery_cfg)
                delivery["public"] = delivery_cfg.get("wp_status", "draft") == "publish"
            elif name == "note":
                from . import browser
                browser_started = True
                url = browser.note_draft(post, publish=delivery_cfg.get("note_publish", False), headless=c.get("browser_headless", True))
                delivery["public"] = bool(delivery_cfg.get("note_publish", False))
            else:
                raise ValueError(f"不明な公開先: {name}")
            delivery.update(status="succeeded", url=url)
            record[name] = url  # 旧履歴との互換性
        except Exception as e:
            # ブラウザや応答の途切れたPOSTでは、投稿済みか確定できない。
            uncertain = browser_started or isinstance(e, UncertainDelivery)
            delivery.update(status="uncertain" if uncertain else "failed", error=str(e))
            print(f"  {name} 失敗: {e}")
        state.save(st)

    # fileだけの運用でもSNS用の文面を保存し、人間が確認できるようにする。
    try:
        if not record.get("tweets"):
            record["tweets"] = writer.thread(post, _public_url(record), c)
        if not record["tweets"]:
            raise ValueError("Xの下書き文面が空です")
        record["draft_file"] = files.tweet_draft(post, record["tweets"], c, record["id"])
        record["draft_status"] = "succeeded"
        record.pop("draft_error", None)
    except Exception as e:
        record.update(draft_status="failed", draft_error=str(e))
        print(f"  X下書き 失敗: {e}")
        state.save(st)
        return
    state.save(st)

    for name in ("x", "x_browser"):
        delivery = deliveries.get(name)
        if not delivery or delivery["status"] not in ("pending", "failed"):
            continue
        delivery.update(status="in_progress")
        delivery.pop("error", None)
        state.save(st)
        browser_started = False
        try:
            if name == "x":
                from .publishers import x
                progress = delivery.setdefault("progress", {})
                url = x.post_thread(record["tweets"], progress=progress, on_progress=lambda: state.save(st))
            else:
                from . import browser
                browser_started = True
                url = browser.x_thread(record["tweets"], headless=c.get("browser_headless", True))
            delivery.update(status="succeeded", url=url)
            record[name] = url
        except Exception as e:
            progress = delivery.get("progress", {})
            uncertain = browser_started or bool(progress.get("ids")) or progress.get("in_flight") is not None
            delivery.update(status="uncertain" if uncertain else "failed", error=str(e))
            print(f"  x 失敗: {e}")
        state.save(st)
    result = ", ".join(f"{name}={d['status']}" for name, d in deliveries.items())
    print(f"  {record['id']} {post['title']}  {result}")


def publish(post, c, st, pseo_key=None, source_id=None):
    existing = _existing_record(st, source_id=source_id, pseo_key=pseo_key)
    if existing is not None:
        return existing
    targets = list(dict.fromkeys(["file", *c.get("publishers", [])]))
    if "x" in targets and "x_browser" in targets:
        raise ValueError("x と x_browser はどちらか一方を選んでください")
    record = {"id": uuid.uuid4().hex[:12], "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
              "title": post["title"], "post": post,
              "draft_status": "pending",
              "publish_config": {"wp_status": c.get("wp_status", "draft"), "note_publish": c.get("note_publish", False)},
              "deliveries": {name: {"status": "pending"} for name in targets}}
    if pseo_key is not None:
        record["pseo_key"] = pseo_key
    if source_id is not None:
        record["source_id"] = source_id
    st["posts"].append(record)
    state.save(st)
    _deliver(record, c, st)
    return record


def do_retry(c, st, post_id=None, limit=10):
    if limit <= 0:
        return
    records = [p for p in st["posts"] if p.get("post") and (not post_id or p.get("id") == post_id)]
    for record in [p for p in records if _retryable(p)][:limit]:
        _deliver(record, c, st)
    for record in records:
        uncertain = [n for n, d in record["deliveries"].items() if d["status"] in ("uncertain", "in_progress")]
        if uncertain:
            print(f"  {record['id']}: {', '.join(uncertain)} は結果要確認。自動再送しません")


def _pseo_key(row):
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pseo_rows(path, done, limit):
    """不正なCSV行を除外し、正常な未生成行だけを指定件数まで返す。"""
    if limit == 0:
        return []
    rows, keys = [], set(done)
    with open(path, encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        headers = reader.fieldnames
        if not headers or any(not name.strip() for name in headers) or len(headers) != len(set(headers)):
            raise ValueError("CSVのヘッダーには重複のない空欄以外の列名を指定してください")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                print(f"  CSV {reader.line_num}行: 列数がヘッダーと一致しないためスキップ")
                continue
            if not any(value.strip() for value in row.values()):
                continue
            key = _pseo_key(row)
            if key in keys or "|".join(row.values()) in keys:
                continue
            rows.append(row)
            keys.add(key)
            if len(rows) >= limit:
                break
    return rows


def do_collect(c, st):
    n = state.enqueue(st, sources.collect(c["sources"]))
    print(f"新規 {n}件 / キュー {len(st['queue'])}件")


def do_write(c, st, n):
    for _ in range(min(n, len(st["queue"]))):
        item = state.next_item(st)
        if not item:
            break
        if _existing_record(st, source_id=item["id"]) is not None:
            print(f"  {item['title']}: 生成済みの記録があります。配信失敗は retry で再試行してください")
            state.save(st)
            continue
        print(f"▶ [{item['source']}] {item['title']}")
        try:
            post = writer.article(item, sources.fetch_body(item["url"]) or item.get("summary", ""), c)
            publish(post, c, st, source_id=item["id"])
        except Exception as e:
            print(f"  ✗ {e}")
            if _existing_record(st, source_id=item["id"]) is None:
                item["tries"] = item.get("tries", 0) + 1
                if item["tries"] < 3:  # 記録作成前の生成失敗だけ再キューする。
                    st["queue"].append(item)
            else:
                print("  生成済みの記録を保持しました。元記事は再生成せず配信結果を確認してください")
        state.save(st)
        time.sleep(c.get("interval_sec", 5))


def main():
    ap = argparse.ArgumentParser(prog="engine", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("collect")
    for name in ("write", "run"):
        sp.add_parser(name).add_argument("-n", type=nonnegative_int, default=None)
    p = sp.add_parser("pseo"); p.add_argument("csv"); p.add_argument("--limit", type=nonnegative_int, default=10)
    p = sp.add_parser("retry", help="失敗した公開先のみ再試行（結果不明・部分投稿は除外）")
    p.add_argument("post_id", nargs="?"); p.add_argument("-n", type=nonnegative_int, default=10)
    sp.add_parser("login").add_argument("site", choices=["note", "x"])
    sp.add_parser("status")
    a = ap.parse_args()
    if ((a.cmd in ("write", "run", "retry") and a.n == 0) or
            (a.cmd == "pseo" and a.limit == 0)):
        return
    c = cfg()
    if a.cmd in ("write", "run"):
        try:
            count = nonnegative_int(a.n if a.n is not None else c.get("posts_per_run", 2))
        except argparse.ArgumentTypeError as error:
            ap.error(f"posts_per_run: {error}")
        if count == 0:
            return
    st = state.load()

    if a.cmd in ("collect", "run"):
        do_collect(c, st); state.save(st)
    if a.cmd in ("write", "run"):
        do_write(c, st, count)
    if a.cmd == "pseo":
        done = set(st.get("pseo_done", {})) | {p.get("pseo_key") for p in st["posts"]}
        try:
            rows = _pseo_rows(a.csv, done, a.limit)
        except ValueError as error:
            ap.error(str(error))
        for r in rows:
            key = _pseo_key(r)
            if key in done:
                continue
            print(f"▶ {r}")
            try:
                post = writer.pseo(r, c)
                publish(post, c, st, pseo_key=key)
                done.add(key)
            except Exception as e:
                print(f"  ✗ {e}")
            state.save(st)
    if a.cmd == "retry":
        do_retry(c, st, a.post_id, a.n)
    if a.cmd == "login":
        from . import browser
        browser.login(a.site)
    if a.cmd == "status":
        print(f"キュー {len(st['queue'])} / 投稿済み {len(st['posts'])}")
        for p in st["posts"][-5:]:
            statuses = ", ".join(f"{k}={v['status']}" for k, v in p.get("deliveries", {}).items())
            print(f"  {p.get('id', '')} {p['date']} {p['title']} {statuses}")


if __name__ == "__main__":
    main()
