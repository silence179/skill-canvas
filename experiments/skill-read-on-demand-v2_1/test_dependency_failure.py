"""A real native dependency failure must remain available for agent recovery."""
import json
import unittest

from protocol import inject, validate_delivery
from test_protocol import policy, activated, images, tool_call


class DependencyFailureTests(unittest.TestCase):
    def test_native_ripgrep_error_is_preserved_without_activation(self):
        p = policy()
        d = activated(p)
        d["messages"][-1]["content"] = "ripgrep execution failed"
        self.assertIs(inject(d, p), d)
        self.assertEqual(validate_delivery(d, p), [])
        self.assertFalse(images(d))

    def test_parallel_error_and_read_then_file_fallback(self):
        p = policy()
        d = activated(p)
        d["messages"][-1]["content"] = "ripgrep execution failed"
        d["messages"][-2]["tool_calls"].append(tool_call("config", "config.json", "read"))
        d["messages"].append(dict(role="tool", tool_call_id="config", content='{"block_size":512}'))
        self.assertIs(inject(d, p), d)
        d["messages"] += [dict(role="assistant", content=None, tool_calls=[dict(id="fallback", type="function",
            function=dict(name="bash", arguments=json.dumps({"command": "cat /skills/alpha/SKILL.md"})))]),
            dict(role="tool", tool_call_id="fallback", content=p["assets"][0]["skill_text"])]
        out = inject(d, p)
        self.assertEqual(len(images(out)), 1)
        self.assertEqual(out["messages"][:-1], d["messages"])
        loads = validate_delivery(out, p)
        self.assertEqual([(x["skill"], x["call_id"], x["trigger"]) for x in loads], [("alpha", "fallback", "file_read")])


if __name__ == "__main__":
    unittest.main()
