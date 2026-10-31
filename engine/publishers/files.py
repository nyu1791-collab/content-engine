"""Markdown(frontmatter付き)で output/ に保存。Hugo/Astro/Jekyll にそのまま置ける＝GitHub Pages で無料ブログ化も可。"""
from datetime import datetime
import json
from pathlib import Path

import yaml


def publish(post, cfg):
    d = Path(cfg.get("output_dir", "output"))
    d.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    path = d / f"{date}-{post['slug']}.md"
    i = 2
    while path.exists():  # 同日同スラッグは上書きしない
        path = d / f"{date}-{post['slug']}-{i}.md"; i += 1
    metadata = {"title": post["title"], "date": date, "description": post.get("description", ""),
                "tags": post.get("tags", [])}
    header = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
    path.write_text(f'---\n{header}---\n\n{post["body"]}\n',
                    encoding="utf-8")
    return str(path)


def tweet_draft(post, tweets, cfg, post_id):
    """公開せず、レビュー用のX文面を安定したファイル名で保存する。"""
    d = Path(cfg.get("output_dir", "output"))
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{post_id}-tweets.json"
    data = {"post_id": post_id, "status": "draft", "title": post["title"],
            "source_url": post.get("source_url", ""), "tweets": tweets}
    pending = path.with_suffix(".json.tmp")
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    pending.replace(path)
    return str(path)
