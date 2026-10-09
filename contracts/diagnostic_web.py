# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Temporary diagnostic for the pinned SDK's public HTTP endpoint access.

Only submit public URLs and request bodies: arguments and reports are public.
This contract neither accepts nor supplies authentication headers.
"""

from genlayer import *
import json


class WebDiagnostic(gl.Contract):
    report: str

    def __init__(self):
        self.report = ""

    @gl.public.write
    def check(self, url: str, body: str) -> str:
        if not url.startswith("https://") or len(url) > 2048:
            raise ValueError("public HTTPS URL required")
        if len(body.encode("utf-8")) > 24576:
            raise ValueError("request body too large")

        def run():
            stage = "post"
            try:
                response = gl.nondet.web.post(
                    url, body=body, headers={"Content-Type": "application/json"}
                )
                stage = "response"
                payload = b"" if response.body is None else bytes(response.body)
                return json.dumps({
                    "ok": True,
                    "stage": stage,
                    "status": int(response.status),
                    "body_bytes": len(payload),
                    "body_prefix": payload[:400].decode("utf-8", errors="replace"),
                }, sort_keys=True)
            except Exception as error:
                return json.dumps({
                    "ok": False,
                    "stage": stage,
                    "error_type": type(error).__name__,
                    "error": str(error)[:1200],
                }, sort_keys=True)

        self.report = gl.eq_principle.strict_eq(run)
        return self.report

    @gl.public.write
    def check_llm(self) -> str:
        def run():
            try:
                answer = gl.nondet.exec_prompt("Return only OK")
                return json.dumps({"ok": True, "answer": str(answer)[:400]}, sort_keys=True)
            except Exception as error:
                return json.dumps({
                    "ok": False,
                    "error_type": type(error).__name__,
                    "error": str(error)[:1200],
                }, sort_keys=True)

        self.report = gl.eq_principle.strict_eq(run)
        return self.report

    @gl.public.view
    def read(self) -> str:
        return self.report
