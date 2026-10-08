"""Live smoke against Ollama through the web API, in-process (not for CI).

``python scripts/smoke_live.py [pdf] [student_id]`` queues ``POST /api/process`` and
polls ``/api/jobs/{id}`` until the job finishes. The PDF must sit in ``input.jawaban_dir``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.web.main import create_app  # noqa: E402

POLL_SECONDS = 2.0


def main(argv: list[str]) -> int:
    pdf = argv[0] if argv else "smoke_inequality.pdf"
    student_id = argv[1] if len(argv) > 1 else "smoke_001"
    with TestClient(create_app()) as client:
        response = client.post("/api/process", json={"pdf": pdf, "student_id": student_id})
        if response.status_code != 202:
            print(f"ERROR {response.status_code}: {response.text}", file=sys.stderr)
            return 1
        status_url = response.json()["status_url"]
        seen = 0
        while True:
            job = client.get(status_url).json()
            for event in job["events"][seen:]:
                print(event["message"])
            seen = len(job["events"])
            if job["status"] in ("done", "failed"):
                break
            time.sleep(POLL_SECONDS)
    if job["status"] == "failed":
        print(f"ERROR: {job['error']}", file=sys.stderr)
        return 1
    print(f"Selesai: {job['next_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
