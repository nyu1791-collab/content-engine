"""X API v2でスレッド投稿。利用権限・投稿枠・料金は契約に従う。"""
import os


def post_thread(tweets, progress=None, on_progress=None):
    import tweepy
    c = tweepy.Client(consumer_key=os.environ["X_API_KEY"], consumer_secret=os.environ["X_API_SECRET"],
                      access_token=os.environ["X_ACCESS_TOKEN"], access_token_secret=os.environ["X_ACCESS_SECRET"])
    progress = progress if progress is not None else {}
    ids = progress.setdefault("ids", [])
    if ids or progress.get("in_flight") is not None:
        raise RuntimeError("部分投稿・送信結果不明のスレッドはX上で確認してください")
    prev, first = None, None
    for index, t in enumerate(tweets):
        progress["in_flight"] = index
        if on_progress:
            on_progress()
        try:
            r = c.create_tweet(text=t, in_reply_to_tweet_id=prev)
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            # 明確な拒否は投稿されていない。408や通信断は結果不明のまま保留する。
            if isinstance(status, int) and 400 <= status < 500 and status != 408:
                progress.pop("in_flight", None)
                if on_progress:
                    on_progress()
            raise
        prev = r.data["id"]
        first = first or prev
        ids.append(prev)
        progress.pop("in_flight", None)
        if on_progress:
            on_progress()
    return f"https://x.com/i/status/{first}"
