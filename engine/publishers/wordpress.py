"""WordPress REST API で投稿（アプリケーションパスワード認証）。"""
import os

import markdown
import requests

from . import UncertainDelivery


def _tag_ids(base, auth, names):
    ids = []
    for n in names[:5]:
        r = requests.get(f"{base}/tags", params={"search": n}, auth=auth, timeout=20).json()
        hit = next((t for t in r if t["name"] == n), None)
        if not hit:
            hit = requests.post(f"{base}/tags", json={"name": n}, auth=auth, timeout=20).json()
        if "id" in hit:
            ids.append(hit["id"])
    return ids


def publish(post, cfg):
    base = os.environ["WP_URL"].rstrip("/") + "/wp-json/wp/v2"
    auth = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
    html = markdown.markdown(post["body"], extensions=["tables", "fenced_code"])
    data = {"title": post["title"], "content": html, "slug": post["slug"], "excerpt": post.get("description", ""),
            "status": cfg.get("wp_status", "draft"), "tags": _tag_ids(base, auth, post.get("tags", []))}
    if cat := os.getenv("WP_CATEGORY_ID"):
        data["categories"] = [int(cat)]
    try:
        r = requests.post(f"{base}/posts", json=data, auth=auth, timeout=60)
    except requests.RequestException as e:
        raise UncertainDelivery("WordPress投稿の応答を受信できませんでした。管理画面で投稿の有無を確認してください") from e
    if r.status_code >= 500 or r.status_code == 408:
        raise UncertainDelivery(f"WordPress投稿の結果が不明です（HTTP {r.status_code}）。管理画面で確認してください")
    r.raise_for_status()
    try:
        link = r.json()["link"]
        if not isinstance(link, str) or not link:
            raise ValueError("投稿URLなし")
        return link
    except (ValueError, KeyError, TypeError) as e:
        raise UncertainDelivery("WordPressから投稿URLを取得できませんでした。管理画面で確認してください") from e
