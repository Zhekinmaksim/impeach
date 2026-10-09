#!/usr/bin/env python3
"""Serve the scripted subjects as an OpenAI-shaped chat endpoint.

    python3 scripts/stub_endpoint.py --port 8787
    curl -s localhost:8787/memoriser/v1/chat/completions \\
      -d '{"messages":[{"role":"user","content":"hello"}]}'

Paths: /memoriser/…, /capable/…, /neither/…, /dead/…

Two uses. Against a local GenLayer node it lets the whole lifecycle run end to
end with real consensus and no model bill. Behind a public HTTPS tunnel it is a
subject whose verdict is known in advance, which is the honest way to show the
CONTAMINATED path on Bradbury: a lookup table, declared as one, convicted as one.
It is not a model and a case against it proves the court, not a finding.
"""

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test"))

import population as pop  # noqa: E402

CORPUS = pop.load_corpus()
SUBJECTS = {
    "memoriser": pop.Memoriser(CORPUS),
    "capable": pop.Capable(CORPUS),
    "neither": pop.Neither(CORPUS),
    "dead": pop.Dead(CORPUS),
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        name = self.path.strip("/").split("/")[0]
        subject = SUBJECTS.get(name)
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        if subject is None:
            status, payload = 404, b'{"error":"no such subject"}'
        else:
            try:
                status, payload = subject.handle(body)
            except Exception as exc:  # noqa: BLE001
                status, payload = 400, json.dumps({"error": str(exc)}).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.path, fmt % args))


def main() -> int:
    ap = argparse.ArgumentParser(prog="stub_endpoint")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    print("serving %s on http://%s:%d" % (", ".join(sorted(SUBJECTS)), args.host, args.port))
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
