"""Regression checks for SkillCanvas forced-prefix-v1 delivery."""

import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest

from delivery_protocol import (
    SkillDeliveryError, attach_logger_hook, inject, is_helper, prefix_content,
    validate_delivery, validate_policy,
)
from delivery_runner import audit_rollout, callback_source, load_policy
from prepare import HERE


def request():
    return {
        "model": "runtime-deepseek-deepseek-flash",
        "messages": [{"role": "system", "content": "Coding agent"},
                     {"role": "user", "content": "Original task, unchanged"}],
        "tools": [{"type": "function", "function": {
            "name": "noop", "parameters": {"type": "object", "properties": {}},
        }}],
    }


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = load_policy("text", HERE / "bundles/text")
        cls.image = load_policy("image", HERE / "bundles/image")

    def test_legacy_request_is_rejected_and_injection_preserves_task(self):
        """Guards the missing image exposure in the 2026-11-14 old image run."""
        original = request()
        with self.assertRaises(SkillDeliveryError):
            validate_delivery(original, self.image)
        result = inject(original, self.image)
        validate_delivery(result, self.image)
        self.assertEqual(result["messages"][-1], original["messages"][-1])
        self.assertEqual(len(original["messages"]), 2)
        self.assertEqual(inject(result, self.image), result)

    def test_both_figures_precede_identical_full_guides(self):
        text = prefix_content(self.text)
        image = prefix_content(self.image)
        self.assertEqual(text[-2:], image[-2:])
        self.assertEqual(sum(p["type"] == "image_url" for p in image), 2)
        self.assertEqual(sum(p["type"] == "image_url" for p in text), 0)
        self.assertTrue(all(p["type"] == "text" for p in image[-2:]))
        self.assertEqual([x["guide_sha256"] for x in self.text["assets"]],
                         [x["guide_sha256"] for x in self.image["assets"]])

    def test_missing_altered_or_reordered_images_fail(self):
        supplied = inject(request(), self.image)
        for mutation in ("missing", "altered", "reordered"):
            with self.subTest(mutation=mutation):
                data = copy.deepcopy(supplied)
                parts = data["messages"][1]["content"]
                if mutation == "missing":
                    parts.pop(2)
                elif mutation == "altered":
                    parts[2]["image_url"]["url"] = "data:image/png;base64,eA=="
                else:
                    parts[2], parts[-1] = parts[-1], parts[2]
                with self.assertRaises(SkillDeliveryError):
                    validate_delivery(data, self.image)

    def test_bad_local_assets_cannot_launch(self):
        bad = copy.deepcopy(self.image)
        bad["assets"][0]["image_data"] = "malformed"
        with self.assertRaises(SkillDeliveryError):
            validate_policy(bad)

    def test_known_title_is_unchanged_but_unknown_requests_fail_closed(self):
        title = {"messages": [{"role": "system", "content": "You are a title generator."},
                              {"role": "user", "content": "Title please"}]}
        self.assertIs(inject(title, self.image), title)
        with self.assertRaises(SkillDeliveryError):
            inject({"messages": [{"role": "user", "content": "Unknown thread"}]}, self.image)

    def test_original_proxy_guards_are_still_called_and_not_bypassed(self):
        class ExistingLogger:
            async def async_pre_call_hook(self, key, cache, data, call_type):
                validate_delivery(data, DeliveryTests.image)
                raise PermissionError("existing routing/budget guard")
        logger = ExistingLogger()
        attach_logger_hook(logger, self.image)
        with self.assertRaisesRegex(PermissionError, "existing routing/budget guard"):
            asyncio.run(logger.async_pre_call_hook(None, None, request(), "acompletion"))

    def test_proxy_internal_metadata_is_not_copied_or_replaced(self):
        class OpaqueProxyState:
            def __deepcopy__(self, memo):
                raise AssertionError("proxy-owned state must remain untouched")
        data = request()
        state = OpaqueProxyState()
        data["metadata"] = state
        self.assertIs(inject(data, self.image)["metadata"], state)

    def test_audit_does_not_accept_a_successful_score_without_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "trajectory").mkdir()
            row = {"request": {"body": request()}, "response": {"status_code": 200}}
            trace = root / "trajectory/llm_trajectory.jsonl"
            trace.write_text(json.dumps(row) + "\n")
            (root / "result.json").write_text(json.dumps({
                "rewards": {"reward": 1}, "error": None,
                "settings_sent": {"main_calls": 1},
            }))
            self.assertFalse(audit_rollout(root, self.image)["valid"])

    def test_native_redaction_of_public_guide_placeholders_is_admitted(self):
        """Guards the false INVALID in the text run 2026-11-14__18-08-54."""
        from benchflow.trajectories.types import redact_trajectory_obj
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "trajectory").mkdir()
            body = redact_trajectory_obj(inject(request(), self.image))
            row = {"request": {"body": body}, "response": {"status_code": 200}}
            trace = root / "trajectory/llm_trajectory.jsonl"
            trace.write_text(json.dumps(row) + "\n")
            (root / "result.json").write_text(json.dumps({"settings_sent": {"main_calls": 1}}))
            audit = audit_rollout(root, self.image)
            self.assertTrue(audit["valid"])
            self.assertEqual(audit["redacted_guide_calls"], 1)
            body["messages"][1]["content"].pop(2)
            trace.write_text(json.dumps(row) + "\n")
            self.assertFalse(audit_rollout(root, self.image)["valid"])
            row["request"]["body"] = inject(request(), self.image)
            trace.write_text(json.dumps(row) + "\n")
            self.assertTrue(audit_rollout(root, self.image)["valid"])
            (root / "result.json").write_text(json.dumps({"settings_sent": {"main_calls": 2}}))
            self.assertFalse(audit_rollout(root, self.image)["valid"])

    def test_generated_callback_executes_real_benchflow_hook(self):
        from benchflow.providers.litellm_logging import callback_module_source
        namespace = {"__name__": "skillcanvas_callback_test"}
        exec(compile(callback_source(callback_module_source(), self.image),
                     "<generated-callback>", "exec"), namespace)
        logger = namespace["proxy_handler_instance"]
        result = asyncio.run(logger.async_pre_call_hook(None, None, request(), "acompletion"))
        validate_delivery(result, self.image)
        self.assertFalse(is_helper(result))


if __name__ == "__main__":
    unittest.main()
