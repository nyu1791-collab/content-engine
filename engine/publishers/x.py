"""X(Twitter) API v2 でツリー投稿。Free プランでも投稿は可能（月間上限あり）。"""
import os


def post_thread(tweets):
    import tweepy
    c = tweepy.Client(consumer_key=os.environ["X_API_KEY"], consumer_secret=os.environ["X_API_SECRET"],
                      access_token=os.environ["X_ACCESS_TOKEN"], access_token_secret=os.environ["X_ACCESS_SECRET"])
    prev, first = None, None
    for t in tweets:
        r = c.create_tweet(text=t, in_reply_to_tweet_id=prev)
        prev = r.data["id"]
        first = first or prev
    return f"https://x.com/i/status/{first}"
