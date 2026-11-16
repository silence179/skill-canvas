#!/usr/bin/env python3
"""Check all task prefixes on the HTTP wire; optionally check four images live."""

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
import threading

from study import HERE, ROOT, TASKS
sys.path.insert(0, str(HERE.parent / "uml-flowchart"))
sys.path.insert(0, str(ROOT / "experiments"))
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
from delivery_protocol import public_policy, validate_delivery
from delivery_runner import callback_source, load_policy


async def check(task, live):
    import litellm
    from benchflow.providers.litellm_logging import callback_module_source
    policy = load_policy("image", HERE / "tasks" / task / "bundles/image")
    namespace = {"__name__": "expanded_delivery_smoke"}
    exec(compile(callback_source(callback_module_source(), policy), "<expanded-callback>", "exec"), namespace)
    logger = namespace["proxy_handler_instance"]
    captured = []
    server = None
    if live:
        from env_config import load_env
        load_env(ROOT / ".env")
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise RuntimeError("configured provider key is empty")
        base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    else:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"])) ))
                payload = json.dumps({"id": "local-expanded-smoke", "object": "chat.completion",
                    "created": 1, "model": "deepseek-flash", "choices": [{"index": 0,
                    "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        key, base = "local-no-provider-key", f"http://127.0.0.1:{server.server_port}/v1"
    try:
        data = {"model": "deepseek/deepseek-flash", "max_tokens": 128,
            "messages": [{"role": "system", "content": "You are a coding assistant."},
                         {"role": "user", "content": "Input delivery check only. Do not solve a task or use tools. Reply OK."}],
            "tools": [{"type": "function", "function": {"name": "noop", "description": "Do not use",
                "parameters": {"type": "object", "properties": {}}}}]}
        forwarded = await logger.async_pre_call_hook(None, None, data, "acompletion")
        response = await litellm.acompletion(**forwarded, api_key=key, api_base=base, timeout=45, num_retries=0)
        if not live:
            if len(captured) != 1:
                raise RuntimeError("unexpected number of outbound requests")
            validate_delivery(captured[0], policy)
        return {"valid": True, "task": task, "kind": "live" if live else "local-wire",
            "policy": public_policy(policy), "image_count": len(policy["assets"]),
            "reply": response.choices[0].message.content,
            "usage": response.usage.model_dump() if live else None}
    finally:
        if server:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        tasks = ("energy-market-pricing",) if args.live else TASKS
        rows = [asyncio.run(check(task, args.live)) for task in tasks]
        target = ROOT / ".runtime/uml-expanded" / ("live-smoke.json" if args.live else "local-wire-smoke.json")
        target.write_text(json.dumps(rows, indent=2) + "\n")
        print(json.dumps({"valid": True, "tasks": len(rows), "report": str(target)}))
    except Exception as error:
        print(json.dumps({"valid": False, "error_type": type(error).__name__,
                          "status_code": getattr(error, "status_code", None)}))
        raise SystemExit(1)
