#!/usr/bin/env python3
"""Check the generated hook and actual provider wire, optionally with one live call."""

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sys
import threading

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
from delivery_protocol import public_policy, validate_delivery
from delivery_runner import callback_source, load_policy
from prepare import HERE, ROOT


def execute(live=False):
    import litellm
    from benchflow.providers.litellm_logging import callback_module_source

    policy = load_policy("image", HERE / "bundles/image")
    namespace = {"__name__": "skillcanvas_delivery_smoke"}
    exec(compile(callback_source(callback_module_source(), policy),
                 "<skillcanvas-delivery-smoke>", "exec"), namespace)
    logger = namespace["proxy_handler_instance"]
    captured = []
    server = None
    if live:
        sys.path.insert(0, str(ROOT / "experiments"))
        from env_config import load_env
        load_env(ROOT / ".env")
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key.strip():
            raise RuntimeError("DEEPSEEK_API_KEY is empty")
        base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    else:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                captured.append(body)
                payload = json.dumps({
                    "id": "local-wire-smoke", "object": "chat.completion", "created": 1,
                    "model": "deepseek-flash", "choices": [{"index": 0,
                    "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        key, base = "local-test-no-provider-key", f"http://127.0.0.1:{server.server_port}/v1"

    async def call():
        data = {
            "model": "deepseek/deepseek-flash", "max_tokens": 256,
            "messages": [{"role": "system", "content": "You are a coding assistant."},
                         {"role": "user", "content": (
                             "This is only an input-delivery connectivity check. Do not use tools "
                             "or solve any benchmark. Reply exactly OK."
                         )}],
            "tools": [{"type": "function", "function": {
                "name": "noop", "description": "Do not call this connectivity-test tool.",
                "parameters": {"type": "object", "properties": {}},
            }}],
        }
        forwarded = await logger.async_pre_call_hook(None, None, data, "acompletion")
        validate_delivery(forwarded, policy)
        response = await litellm.acompletion(
            **forwarded, api_key=key, api_base=base, timeout=45, num_retries=0,
        )
        return response

    try:
        response = asyncio.run(call())
        if not live:
            if len(captured) != 1:
                raise RuntimeError("expected exactly one local provider request")
            validate_delivery(captured[0], policy)
        report = {
            "kind": "live-provider-smoke" if live else "local-wire-smoke",
            "valid": True, "policy": public_policy(policy),
            "image_count": 2, "guide_count": 2,
            "provider_wire_checked": not live,
            "provider_accepted": True,
            "reply": response.choices[0].message.content,
            "usage": response.usage.model_dump() if live else None,
            "note": "Connectivity evidence only; not a benchmark score or method-gain result.",
        }
        target = ROOT / ".runtime/uml-delivery" / (report["kind"] + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"valid": True, "kind": report["kind"],
                          "image_count": 2, "guide_count": 2, "report": str(target)}, indent=2))
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="one bounded request with the configured DeepSeek key")
    args = parser.parse_args()
    try:
        execute(args.live)
    except Exception as error:
        # Provider exceptions may include request headers. Keep this diagnostic
        # limited to type/status rather than printing credential-bearing text.
        print(json.dumps({"valid": False, "error_type": type(error).__name__,
                          "status_code": getattr(error, "status_code", None)}))
        raise SystemExit(1)
