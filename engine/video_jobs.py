"""テーマの承認から動画制作ジョブを作る。承認された記録だけを job JSON にする。
動画の制作（調査・台本・Colab GPU・YouTube）は voiceBox-Pipeline 側が読んで行う。ここでは制作も公開もしない。
保存先は VIDEO_JOB_DIR（未指定なら yu-lab/media/jobs/video。Gitに入れない）。"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "media" / "jobs" / "video"


def job_dir():
    return Path(os.getenv("VIDEO_JOB_DIR") or DEFAULT_DIR)


def new_request(topic, urls=()):
    """承認依頼に使う動画テーマの記録を作る。URLは https のみ受け付ける。"""
    topic = " ".join(topic.split())
    if not topic:
        raise ValueError("テーマが空です")
    urls = [url.strip() for url in urls if url.strip()]
    for url in urls:
        if not url.startswith("https://"):
            raise ValueError(f"参考URLは https:// で入れてください: {url}")
    body = f"テーマ: {topic}\n" + "\n".join(f"参考URL: {url}" for url in urls)
    return {"id": uuid.uuid4().hex[:12], "kind": "video", "topic": topic, "urls": urls,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "post": {"title": f"動画テーマ: {topic}", "body": body, "source_url": urls[0] if urls else ""},
            "deliveries": {}}


def write_job(record):
    """承認済みの動画テーマを job JSON に書く。voiceBox-Pipeline はこの status が approved のものだけ読む。"""
    directory = job_dir()
    directory.mkdir(parents=True, exist_ok=True)
    job = {"id": record["id"], "status": "approved", "topic": record["topic"], "urls": record["urls"],
           "created": record["date"], "approved_at": record["approval"]["decided"]}
    path = directory / f"{record['id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
