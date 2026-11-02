"""Discord 承認の接続を確認する。トークンやIDの値は表示しない（BotとチャンネルのNameだけ表示）。
使い方: python scripts/check_discord.py"""
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

API = "https://discord.com/api/v10"
KEYS = ("DISCORD_BOT_TOKEN", "DISCORD_APPROVAL_CHANNEL_ID", "DISCORD_APPROVER_ID")


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    values = {k: os.getenv(k, "").strip() for k in KEYS}
    missing = [k for k, v in values.items() if not v]
    if missing:
        print("未設定（.env に入れてください）: " + ", ".join(missing))
        return 1
    if not values["DISCORD_APPROVAL_CHANNEL_ID"].isdigit() or not values["DISCORD_APPROVER_ID"].isdigit():
        print("チャンネルIDとユーザーIDは数字だけで入れてください")
        return 1
    headers = {"Authorization": f"Bot {values['DISCORD_BOT_TOKEN']}", "User-Agent": "content-engine/1.0"}
    me = requests.get(f"{API}/users/@me", headers=headers, timeout=15)
    if me.status_code != 200:
        print(f"Botとして認証できません（{me.status_code}）。トークンを入れ直してください")
        return 1
    print(f"Bot: {me.json().get('username')}")
    channel = requests.get(f"{API}/channels/{values['DISCORD_APPROVAL_CHANNEL_ID']}", headers=headers, timeout=15)
    if channel.status_code != 200:
        print(f"チャンネルが見えません（{channel.status_code}）。Botがサーバーに入っているか、チャンネルIDを確認してください")
        return 1
    print(f"チャンネル: {channel.json().get('name')}")
    print("接続OK。次は CONFIG=config.affiliate.yaml STATE_PATH=data/affiliate_state.json python -m engine approve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
