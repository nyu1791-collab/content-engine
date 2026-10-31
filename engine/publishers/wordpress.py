"""WordPress REST API で投稿（アプリケーションパスワード認証）。"""
import os

import markdown
import requests


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
            "status": cfg.get("wp_status", "publish"), "tags": _tag_ids(base, auth, post.get("tags", []))}
    if cat := os.getenv("WP_CATEGORY_ID"):
        data["categories"] = [int(cat)]
    r = requests.post(f"{base}/posts", json=data, auth=auth, timeout=60)
    r.raise_for_status()
    return r.json()["link"]
