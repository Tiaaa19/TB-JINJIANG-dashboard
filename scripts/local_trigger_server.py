#!/usr/bin/env python3
"""Local-only trigger service for running and publishing TB JINJIANG monitoring."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("TB_MONITOR_PYTHON", "/usr/bin/python3")
PORT = int(os.environ.get("TB_MONITOR_PORT", "8765"))
ALLOWED_ORIGIN = "https://tiaaa19.github.io"
PAGES_URL = "https://tiaaa19.github.io/TB-JINJIANG-dashboard/data/latest.json"

LOCK = threading.Lock()
STATE = {
    "state": "idle",
    "progress": 0,
    "detail": "本机监测服务已就绪",
    "requestedAt": None,
    "updatedAt": None,
    "error": None,
}


def update(**changes: object) -> None:
    with LOCK:
        STATE.update(changes)


def snapshot() -> dict:
    with LOCK:
        return dict(STATE)


def run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def published(requested_at: str) -> bool:
    try:
        req = urllib.request.Request(
            f"{PAGES_URL}?ts={int(time.time())}",
            headers={"Cache-Control": "no-cache", "User-Agent": "TB-JINJIANG-Local-Monitor/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.load(response)
        return payload.get("updatedAt") == requested_at
    except Exception:
        return False


def monitor_and_publish(requested_at: str) -> None:
    try:
        update(state="running", progress=8, detail="正在同步 GitHub 最新版本", error=None)
        run(["git", "pull", "--rebase", "origin", "main"])

        update(progress=18, detail="正在执行公开舆情检索")
        env = os.environ.copy()
        env["MONITOR_REQUESTED_AT"] = requested_at
        run([PYTHON, "scripts/monitor.py"], env=env)

        update(progress=62, detail="检索完成，正在提交监测结果")
        run(["git", "add", "index.html", "data/"])
        status = run(["git", "status", "--porcelain"])
        if status:
            run(["git", "commit", "-m", f"chore: manual monitoring {requested_at}"])
            update(progress=74, detail="正在推送 GitHub")
            run(["git", "push", "origin", "main"])
        else:
            update(progress=74, detail="结果无文件差异，正在确认线上版本")

        update(state="deploying", progress=82, detail="GitHub 已更新，等待 Pages 发布")
        deadline = time.time() + 300
        while time.time() < deadline:
            if published(requested_at):
                update(
                    state="completed",
                    progress=100,
                    detail="正式监测及 GitHub Pages 更新完成",
                    updatedAt=requested_at,
                )
                return
            time.sleep(5)
        raise TimeoutError("等待 GitHub Pages 发布超时")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()[-500:]
        update(state="failed", progress=100, detail="正式监测失败", error=detail)
    except Exception as exc:
        update(state="failed", progress=100, detail="正式监测失败", error=str(exc))


class Handler(BaseHTTPRequestHandler):
    def cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin == ALLOWED_ORIGIN or origin.startswith("http://127.0.0.1") or origin.startswith("http://localhost"):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def respond(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/status":
            self.respond(404, {"error": "not_found"})
            return
        self.respond(200, snapshot())

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/run":
            self.respond(404, {"error": "not_found"})
            return
        current = snapshot()
        if current["state"] in {"running", "deploying"}:
            self.respond(202, current)
            return
        requested_at = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")
        update(
            state="running",
            progress=2,
            detail="已收到本机正式监测请求",
            requestedAt=requested_at,
            updatedAt=None,
            error=None,
        )
        threading.Thread(target=monitor_and_publish, args=(requested_at,), daemon=True).start()
        self.respond(202, snapshot())

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"TB JINJIANG local trigger listening on http://127.0.0.1:{PORT}")
    server.serve_forever()
