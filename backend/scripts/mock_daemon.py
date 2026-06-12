"""Mock WhatsApp daemon — stands in for a paired 2nd number.

Implements the exact HTTP contract of whatsapp-daemon/src/server.ts, but
instead of sending over WhatsApp it reports state=connected and CAPTURES
every send (image + caption + target group) into an output directory so
you can see precisely what Shmuel's number would have posted.

Run: uv run python scripts/mock_daemon.py [--port 8799] [--out DIR] [--token TOK]
"""
from __future__ import annotations

import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ARGS = argparse.Namespace()


class Handler(BaseHTTPRequestHandler):
    _n = 0

    def log_message(self, *_a):  # silence default stderr noise
        pass

    def _json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _auth_ok(self) -> bool:
        return self.headers.get("x-daemon-token") == ARGS.token

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._json(200, {"ok": True})
        if not self._auth_ok():
            return self._json(401, {"error": "unauthorized"})
        if self.path == "/status":
            return self._json(200, {
                "state": "connected",
                "phone": "+972 50-000-0000 (MOCK 2nd number)",
                "qr": None,
            })
        if self.path == "/groups":
            return self._json(200, {"groups": [
                {"id": "120363000000000001@g.us", "name": "Jerusalem Rentals WA"},
                {"id": "120363000000000002@g.us", "name": "Jerusalem Sales WA"},
            ]})
        return self._json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        if not self._auth_ok():
            return self._json(401, {"error": "unauthorized"})
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/send-group-image":
            Handler._n += 1
            n = Handler._n
            group = body.get("groupId", "?")
            caption = body.get("caption", "")
            png = base64.b64decode(body.get("imageBase64", ""))
            safe = group.replace("@", "_at_").replace("/", "_")
            img_path = ARGS.out / f"{n:02d}_{safe}.png"
            txt_path = ARGS.out / f"{n:02d}_{safe}.caption.txt"
            img_path.write_bytes(png)
            txt_path.write_text(caption, encoding="utf-8")
            print(f"[mock-daemon] SEND IMAGE -> group={group}  "
                  f"image={len(png)}B -> {img_path.name}  caption={len(caption)} chars")
            return self._json(200, {"ok": True, "messageId": f"mock-img-{n}"})

        if self.path == "/send-group":
            Handler._n += 1
            n = Handler._n
            group = body.get("groupId", "?")
            message = body.get("message", "")
            safe = group.replace("@", "_at_").replace("/", "_")
            (ARGS.out / f"{n:02d}_{safe}.text.txt").write_text(message, encoding="utf-8")
            print(f"[mock-daemon] SEND TEXT  -> group={group}  message={len(message)} chars")
            return self._json(200, {"ok": True, "messageId": f"mock-txt-{n}"})

        return self._json(404, {"error": "not_found"})


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8799)
    p.add_argument("--out", default="autopost-out")
    p.add_argument("--token", default="mock-daemon-token")
    p.parse_args(namespace=ARGS)
    ARGS.out = Path(ARGS.out)
    ARGS.out.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler)
    print(f"[mock-daemon] listening on http://127.0.0.1:{ARGS.port} "
          f"(token={ARGS.token}) -> capturing to {ARGS.out}/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
