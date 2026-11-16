"""Verify serialized local HTTP payloads, with no real provider or benchmark.

Native tool-result fixtures follow pinned OpenCode 1.19.5 skill.ts. This checks
the actual BenchFlow callback + LiteLLM request serialization, not agent choice.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import threading

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from prepare import HERE, TASKS, CRYSTAL, build, load_policy
from protocol import digest, public_policy, validate_delivery
from runner import callback_source


def image_count(data):
    return sum(p.get("type") == "image_url" for m in data["messages"]
               if isinstance(m.get("content"), list) for p in m["content"])


def native_result(asset, call_id):
    name = asset["skill"]
    return {"role": "tool", "tool_call_id": call_id,
            "content": f'<skill_content name="{name}">\n# Skill: {name}\n\n{asset["body"]}\n\n'
                       f'Base directory for this skill: /skills/{name}\n'
                       'Relative paths in this skill are relative to this base directory.\n'
                       '<skill_files>\n</skill_files>\n</skill_content>'}


async def main():
    import litellm
    from benchflow.providers.litellm_logging import callback_module_source
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            payload = json.dumps(dict(id="local-on-demand-check", object="chat.completion", created=1,
                model="deepseek-flash", choices=[dict(index=0, message=dict(role="assistant", content="OK"), finish_reason="stop")],
                usage=dict(prompt_tokens=1, completion_tokens=1, total_tokens=2))).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    rows = []
    base_source = callback_module_source()
    try:
        for task in TASKS:
            selections = [("text", "uml-v1"), ("image", "uml-v1")]
            if task != CRYSTAL:
                selections += [("image", "uml-v2"), ("image", "structure-v3")]
            for arm, figures in selections:
                policy = load_policy(build(task, arm, figures))
                ns = {"__name__": "skillcanvas_on_demand_wire"}
                exec(compile(callback_source(base_source, policy), "<on-demand-proxy>", "exec"), ns)
                logger = ns["proxy_handler_instance"]
                data = dict(model="deepseek/deepseek-flash", max_tokens=8, messages=[
                    dict(role="system", content="Skills are available by name and description; load them with the skill tool."),
                    dict(role="user", content="Offline protocol fixture. No task solving.")],
                    tools=[dict(type="function", function=dict(name="skill", description="Load a skill", parameters={
                        "type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}))])
                cases = []

                async def send(label, expected_images, expected_loads):
                    forwarded = await logger.async_pre_call_hook(None, None, data, "acompletion")
                    before = len(captured)
                    await litellm.acompletion(**forwarded, api_key="local-no-provider-key",
                        api_base=f"http://127.0.0.1:{server.server_port}/v1", num_retries=0, timeout=20)
                    assert len(captured) == before + 1
                    body = captured[-1]
                    loads = validate_delivery(body, policy)
                    assert image_count(body) == expected_images, (task, arm, label)
                    assert len(loads) == expected_loads
                    cases.append(dict(case=label, images=image_count(body), active_skill_calls=len(loads),
                                      payload_sha256=digest(json.dumps(body, sort_keys=True).encode())))

                await send("before_any_activation", 0, 0)
                # Activate every skill in the task individually. At each point
                # only already successful calls may contribute image payloads.
                for i, asset in enumerate(policy["assets"], 1):
                    cid = "local_skill_" + str(i)
                    data["messages"] += [dict(role="assistant", content=None, tool_calls=[dict(
                        id=cid, type="function", function=dict(name="skill", arguments=json.dumps({"name": asset["skill"]})))]),
                        native_result(asset, cid)]
                    await send("after_" + asset["skill"], i if arm == "image" else 0, i)
                data["messages"].append(dict(role="assistant", content="Continue after loaded skills."))
                await send("history_replay_no_extra_activation", len(policy["assets"]) if arm == "image" else 0, len(policy["assets"]))
                rows.append(dict(task=task, arm=arm, figures=figures if arm == "image" else None,
                                 policy=public_policy(policy), cases=cases, valid=True))
    finally:
        server.shutdown()
        server.server_close()
    report = dict(valid=True, scope="Local HTTP serialization using synthetic native skill results; no actual OpenCode process, provider or benchmark executed.",
                  condition_count=len(rows), local_http_calls=len(captured), conditions=rows)
    (HERE / "wire-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(valid=True, conditions=len(rows), local_http_calls=len(captured), paid_model_calls=0)))


if __name__ == "__main__":
    asyncio.run(main())
