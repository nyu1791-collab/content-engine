"""Markdown(frontmatter付き)で output/ に保存。Hugo/Astro/Jekyll にそのまま置ける＝GitHub Pages で無料ブログ化も可。"""
from datetime import datetime
from pathlib import Path


def publish(post, cfg):
    d = Path(cfg.get("output_dir", "output"))
    d.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    path = d / f"{date}-{post['slug']}.md"
    tags = ", ".join(f'"{t}"' for t in post.get("tags", []))
    title = post["title"].replace('"', "'")
    desc = post.get("description", "").replace('"', "'")
    path.write_text(f'---\ntitle: "{title}"\ndate: {date}\ndescription: "{desc}"\ntags: [{tags}]\n---\n\n{post["body"]}\n',
                    encoding="utf-8")
    return str(path)
