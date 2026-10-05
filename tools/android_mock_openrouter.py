"""A stand-in for OpenRouter when testing the Android app in the emulator, so no real API key is involved.

The emulator reaches the host as 10.0.2.2. Point the debug app at it with files/dev.json:
  {"api_base": "http://10.0.2.2:8765/api/v1", "api_key": "test-key"}

Usage: uv run python tools/android_mock_openrouter.py [--port 8765]
Only request type, model and size are logged; transcripts and hints stay out of logs.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TRANSCRIPT = "嗯，帮我在 cloud code 里面跑一下 uv sync，然后用 ptest 测一下。"
CLEANED = "帮我在 Claude Code 里面跑一下 uv sync，然后用 pytest 测一下。"
TRANSLATED = "Please run uv sync in Claude Code, then test it with pytest."


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # /key (warm-up, key check, usage) and /credits
        if self.headers.get("Authorization") == "Bearer bad-key":
            self.send_response(401)
            self.end_headers()
            return
        if self.path.endswith("/credits"):
            self._send({"data": {"total_credits": 10.0, "total_usage": 1.2345}})
        else:
            self._send({"data": {"usage": 0.42, "usage_daily": 0.0123, "usage_monthly": 0.31, "limit_remaining": None}})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path.endswith("/audio/transcriptions"):
            audio = len(body.get("input_audio", {}).get("data", ""))
            print(f"STT model={body.get('model')} audio_b64={audio}", flush=True)
            self._send({"text": TRANSCRIPT, "usage": {"cost": 0.001, "seconds": 6}})
            return
        system = body["messages"][0]["content"]
        user = body["messages"][-1]["content"]
        kind = (
            "ask"
            if "<spoken>" in user
            else "translate"
            if system.startswith("You are the translation stage")
            else "dictate"
        )
        print(f"CHAT model={body.get('model')} kind={kind}", flush=True)
        text = TRANSLATED if kind == "translate" else CLEANED
        if kind == "ask":
            text = json.dumps(
                {"action": "answer", "text": "**巴黎**是法国的首都。\n- 人口约 210 万\n- 位于 `塞纳河` 畔"},
                ensure_ascii=False,
            )
        self._send({"model": body.get("model"), "choices": [{"message": {"content": text}}], "usage": {"cost": 0.0002}})

    def log_message(self, *_args) -> None:  # the prints above are the log
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    print(f"mock OpenRouter on :{args.port}", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
