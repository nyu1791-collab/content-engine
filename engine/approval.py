"""Discord で公開を承認する。承認者本人の返信だけを受け付ける。
BOT は承認依頼の投稿と返信の読み取りだけに使う（記事の公開はしない）。"""
import os
import re

import requests

API = "https://discord.com/api/v10"
REPLY = re.compile(r"^(承認|却下)\s+([0-9a-f]{12})$")


def _settings():
    values = {k: os.getenv(k, "").strip() for k in ("DISCORD_BOT_TOKEN", "DISCORD_APPROVAL_CHANNEL_ID", "DISCORD_APPROVER_ID")}
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise ValueError("Discord承認の設定が不足: " + ", ".join(missing))
    return values


def _call(method, path, values, **kwargs):
    headers = {"Authorization": f"Bot {values['DISCORD_BOT_TOKEN']}", "User-Agent": "content-engine/1.0"}
    url = f"{API}/channels/{values['DISCORD_APPROVAL_CHANNEL_ID']}/{path}"
    response = requests.request(method, url, headers=headers, timeout=15, **kwargs)
    response.raise_for_status()
    return response.json()


def request(record):
    """承認依頼を1件投稿し、Discord のメッセージ番号を返す。"""
    values = _settings()
    post = record["post"]
    approver = values["DISCORD_APPROVER_ID"]
    text = (f"<@{approver}> 【公開の承認】{post['title']}\n"
            f"記録ID: {record['id']}\n"
            f"出典: {post.get('source_url', '')}\n"
            f"冒頭: {post.get('body', '')[:300]}\n\n"
            f"公開するなら「承認 {record['id']}」、やめるなら「却下 {record['id']}」と返信してください。")
    # 承認者本人だけにメンションする（携帯の通知が届くように。他の人は呼ばない）
    message = _call("POST", "messages", values, json={"content": text[:1900], "allowed_mentions": {"users": [approver]}})
    return message["id"]


def decisions(waiting_ids):
    """承認者本人が書いた「承認 ID」「却下 ID」だけを読む。同じIDは新しい返信を優先する。"""
    if not waiting_ids:
        return {}
    values = _settings()
    messages = _call("GET", "messages", values, params={"limit": 100})
    decided = {}
    for message in messages:  # Discord は新しい順で返す
        if message.get("author", {}).get("id") != values["DISCORD_APPROVER_ID"]:
            continue
        match = REPLY.match(message.get("content", "").strip())
        if match and match.group(2) in waiting_ids and match.group(2) not in decided:
            decided[match.group(2)] = "approved" if match.group(1) == "承認" else "rejected"
    return decided
