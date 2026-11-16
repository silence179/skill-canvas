"""Exercise real activation boundaries; no provider, Docker or task execution."""
import asyncio
import base64
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from protocol import (METHOD, MARKER, LEGACY_MARKER, SkillDeliveryError, attach_logger_hook,
                      digest, inject, policy_id, skill_body, validate_delivery, validate_policy)
from prepare import build, load_policy
from runner import audit_rollout, callback_source


def policy(arm="image"):
    assets = []
    for name in ("alpha", "beta"):
        text = f"---\nname: {name}\ndescription: short catalog entry\n---\n\n# {name}\nComplete native instructions for {name}.\n"
        a = dict(skill=name, skill_text=text, body=skill_body(text), skill_sha256=digest(text.encode()))
        if arm == "image":
            png = b"\x89PNG\r\n\x1a\n" + name.encode()
            a.update(image_data=base64.b64encode(png).decode(), image_sha256=digest(png))
        assets.append(a)
    p = dict(method=METHOD, arm=arm, assets=assets)
    p["id"] = policy_id(p)
    return p


def request():
    return {"model": "deepseek-flash", "messages": [
        {"role": "system", "content": "Available skills: alpha, beta (short descriptions only)."},
        {"role": "user", "content": "Original task"}],
        "tools": [{"type": "function", "function": {"name": "skill", "parameters": {
            "type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}}]}


def tool_call(cid, name, function="skill"):
    return {"id": cid, "type": "function", "function": {"name": function, "arguments": json.dumps({"name": name})}}


def native_result(p, cid, name):
    body = next(a["body"] for a in p["assets"] if a["skill"] == name)
    return {"role": "tool", "tool_call_id": cid,
            "content": f'<skill_content name="{name}">\n# Skill: {name}\n\n{body}\n\nBase directory for this skill: /skills/{name}\n<skill_files>\n</skill_files>\n</skill_content>'}


def activated(p):
    d = request()
    d["messages"] += [{"role": "assistant", "content": None, "tool_calls": [tool_call("a1", "alpha")]},
                      native_result(p, "a1", "alpha")]
    return d


def images(d):
    return [p for m in d["messages"] if isinstance(m.get("content"), list)
            for p in m["content"] if p.get("type") == "image_url"]


class ActivationTests(unittest.TestCase):
    def test_before_activation_exact_native_request_is_preserved(self):
        d = request()
        self.assertIs(inject(d, policy()), d)
        self.assertEqual(validate_delivery(d, policy()), [])
        self.assertFalse(images(d))
        self.assertNotIn("Complete native instructions", json.dumps(d))

    def test_only_called_skill_loaded_with_original_native_text(self):
        p = policy()
        d = activated(p)
        result = inject(d, p)
        self.assertEqual(result["messages"][:-1], d["messages"])
        self.assertEqual(len(images(result)), 1)
        self.assertEqual(images(result)[0]["image_url"]["url"].split(",")[1], p["assets"][0]["image_data"])
        self.assertNotIn(p["assets"][1]["body"], json.dumps(result))
        self.assertEqual(validate_delivery(result, p)[0]["skill"], "alpha")

    def test_later_rounds_replay_one_attachment_without_accumulating_copies(self):
        p = policy()
        raw = activated(p)
        first = inject(raw, p)
        self.assertEqual(inject(first, p), first)
        raw["messages"] += [{"role": "assistant", "content": "Continue working"}]
        later = inject(raw, p)
        self.assertEqual(len(images(later)), 1)
        self.assertEqual(later["messages"][-1]["content"], "Continue working")

    def test_parallel_skill_results_wait_for_complete_batch(self):
        p = policy()
        d = request()
        d["messages"] += [{"role": "assistant", "tool_calls": [tool_call("a", "alpha"), tool_call("b", "beta")]},
                          native_result(p, "b", "beta"), native_result(p, "a", "alpha")]
        out = inject(d, p)
        self.assertEqual(out["messages"][:-1], d["messages"])
        self.assertEqual(len(images(out)), 2)
        self.assertEqual([x["skill"] for x in validate_delivery(out, p)], ["beta", "alpha"])

    def test_parallel_normal_tool_is_not_interrupted_by_media(self):
        p = policy()
        d = activated(p)
        d["messages"][-2]["tool_calls"].append(tool_call("r", "file", "read"))
        d["messages"].append({"role": "tool", "tool_call_id": "r", "content": "Read result"})
        out = inject(d, p)
        self.assertEqual(out["messages"][-2], d["messages"][-1])
        self.assertTrue(out["messages"][-1]["content"][0]["text"].startswith(MARKER))

    def test_text_control_keeps_native_skill_results_unchanged(self):
        p = policy("text")
        d = activated(p)
        self.assertIs(inject(d, p), d)
        self.assertEqual(len(validate_delivery(d, p)), 1)
        self.assertFalse(images(d))

    def test_failed_native_skill_call_loads_nothing(self):
        p = policy()
        d = activated(p)
        d["messages"][-1]["content"] = 'Error: Skill "alpha" not found'
        self.assertEqual(inject(d, p), d)
        self.assertEqual(validate_delivery(d, p), [])

    def test_orphan_result_wrong_name_and_missing_body_fail(self):
        p = policy()
        for kind in ("orphan", "wrong-name", "missing-body", "other-tool"):
            d = activated(p)
            if kind == "orphan":
                del d["messages"][-2]
            elif kind == "wrong-name":
                d["messages"][-2]["tool_calls"][0] = tool_call("a1", "beta")
            elif kind == "missing-body":
                d["messages"][-1]["content"] = '<skill_content name="alpha"># Skill: alpha</skill_content>'
            else:
                d["messages"][-2]["tool_calls"][0]["function"]["name"] = "read"
            with self.subTest(kind=kind), self.assertRaises(SkillDeliveryError):
                inject(d, p)

    def test_missing_changed_duplicated_or_premature_media_rejected(self):
        p = policy()
        good = inject(activated(p), p)
        for kind in ("missing", "changed", "duplicated", "premature"):
            d = copy.deepcopy(good)
            if kind == "missing":
                d["messages"].pop()
            elif kind == "changed":
                d["messages"][-1]["content"][-1]["image_url"]["url"] += "x"
            elif kind == "duplicated":
                d["messages"].append(copy.deepcopy(d["messages"][-1]))
            else:
                d["messages"].insert(1, d["messages"].pop())
            with self.subTest(kind=kind), self.assertRaises(SkillDeliveryError):
                validate_delivery(d, p)

    def test_legacy_prefix_is_not_silently_accepted(self):
        d = request()
        d["messages"].insert(1, {"role": "user", "content": LEGACY_MARKER + " full guides"})
        with self.assertRaises(SkillDeliveryError):
            inject(d, policy())

    def test_compaction_does_not_reload_skills_from_summary_text(self):
        d = request()
        d["messages"].append({"role": "user", "content": "Summary: previously used alpha."})
        self.assertIs(inject(d, policy()), d)
        self.assertFalse(images(d))

    def test_native_compacted_and_interrupted_results_do_not_reactivate(self):
        p = policy()
        for text in ("[Old tool result content cleared]", "[Tool execution was interrupted]",
                     "The skill tool was called with invalid arguments: missing name"):
            d = activated(p)
            d["messages"][-1]["content"] = text
            with self.subTest(text=text):
                self.assertIs(inject(d, p), d)
                self.assertEqual(validate_delivery(d, p), [])
                self.assertFalse(images(d))

    def test_known_helpers_and_native_proxy_state_are_preserved(self):
        d = {"messages": [{"role": "system", "content": "You are a title generator."}]}
        self.assertIs(inject(d, policy()), d)
        opaque = object()
        d = activated(policy())
        d["metadata"] = opaque
        self.assertIs(inject(d, policy())["metadata"], opaque)

    def test_previous_budget_guard_runs_and_cannot_be_bypassed(self):
        class Logger:
            async def async_pre_call_hook(self, key, cache, data, call_type):
                validate_delivery(data, policy())
                raise PermissionError("native budget guard")
        logger = Logger()
        attach_logger_hook(logger, policy())
        with self.assertRaisesRegex(PermissionError, "native budget guard"):
            asyncio.run(logger.async_pre_call_hook(None, None, activated(policy()), "acompletion"))

    def test_real_benchflow_callback_compiles_and_uses_activation_hook(self):
        from benchflow.providers.litellm_logging import callback_module_source
        ns = {"__name__": "on_demand_test"}
        exec(compile(callback_source(callback_module_source(), policy()), "<on-demand-callback>", "exec"), ns)
        logger = ns["proxy_handler_instance"]
        first = asyncio.run(logger.async_pre_call_hook(None, None, request(), "acompletion"))
        self.assertEqual(first["messages"], request()["messages"])
        after = asyncio.run(logger.async_pre_call_hook(None, None, activated(policy()), "acompletion"))
        self.assertEqual(len(images(after)), 1)

    def test_new_native_bundle_restores_skill_md_and_preserves_resources(self):
        with tempfile.TemporaryDirectory() as d:
            text = build("llm-prefix-cache-replay", "text", output_root=d)
            image = build("llm-prefix-cache-replay", "image", output_root=d)
            a, b = load_policy(text), load_policy(image)
            self.assertEqual([x["skill_sha256"] for x in a["assets"]], [x["skill_sha256"] for x in b["assets"]])
            self.assertFalse(list(text.glob("*/GUIDE.md")))
            self.assertNotIn("Skill reading order", (image / "prefix-cache-replay/SKILL.md").read_text())
            self.assertEqual(build("llm-prefix-cache-replay", "image", output_root=d), image)
            (image / "prefix-cache-replay/SKILL.md").write_text("tampered")
            with self.assertRaises(SkillDeliveryError):
                load_policy(image)

    def test_no_skill_activation_is_retained_as_valid_behavior(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "trajectory").mkdir()
            (p / "trajectory/llm_trajectory.jsonl").write_text(json.dumps({"request": {"body": request()}, "response": {"status_code": 200}}) + "\n")
            (p / "result.json").write_text(json.dumps({"settings_sent": {"main_calls": 1}}))
            a = audit_rollout(p, policy())
            self.assertTrue(a["valid"])
            self.assertTrue(a["no_activation"])
            self.assertEqual(a["activations"], [])


if __name__ == "__main__":
    unittest.main()
