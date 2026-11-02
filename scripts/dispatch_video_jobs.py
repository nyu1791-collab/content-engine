"""承認済みの動画ジョブ（VIDEO_JOB_DIR の JSON）を voiceBox-Pipeline の video-job ワークフローへ渡す。
一度渡したジョブは status を dispatched にし、二度と渡さない。失敗したジョブは dispatch_failed にして止める（自動で再送しない）。
使い方（GitHub Actions から呼ぶ）: python scripts/dispatch_video_jobs.py
必要な環境変数: VIDEO_JOB_DIR, VOICEBOX_REPO（例 owner/name）, VOICEBOX_DISPATCH_TOKEN（voiceBox の workflow を動かせる権限）"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

API = "https://api.github.com"
WORKFLOW = "video-job.yml"


def pending_jobs(directory):
    jobs = []
    for path in sorted(Path(directory).glob("*.json")):
        job = json.loads(path.read_text(encoding="utf-8"))
        if job.get("status") == "approved":
            jobs.append((path, job))
    return jobs


def dispatch(job, repo, token, ref="main"):
    """voiceBox の video-job.yml を起動する。成功なら 204 が返る。"""
    url = f"{API}/repos/{repo}/actions/workflows/{WORKFLOW}/dispatches"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    body = {"ref": ref, "inputs": {"job_id": job["id"], "topic": job["topic"],
                                   "urls": "\n".join(job.get("urls", []))}}
    response = requests.post(url, headers=headers, json=body, timeout=30)
    if response.status_code != 204:
        raise RuntimeError(f"voiceBox のワークフローを起動できません（HTTP {response.status_code}）")


def write_status(path, job, status, **extra):
    job.update(status=status, **extra)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main():
    directory = Path(os.environ["VIDEO_JOB_DIR"])
    repo = os.environ["VOICEBOX_REPO"]
    token = os.environ["VOICEBOX_DISPATCH_TOKEN"]
    done = failed = 0
    for path, job in pending_jobs(directory):
        try:
            dispatch(job, repo, token)
        except Exception as e:  # 失敗は記録して止める。再送はしない
            write_status(path, job, "dispatch_failed", error=str(e), failed_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
            print(f"  失敗 {job['id']}: {e}")
            failed += 1
            continue
        write_status(path, job, "dispatched", dispatched_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
        print(f"  渡しました {job['id']} {job['topic']}")
        done += 1
    print(f"渡した {done}件 / 失敗 {failed}件")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
