"""File reading is activation; filenames, references and absent output are not."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from protocol import inject, validate_delivery
from runner import audit_rollout
from test_protocol import policy, request, images


def file_result(p, *, function="bash", arguments=None, output=None):
    d = request()
    args = arguments or {"command": "cat /skills/alpha/SKILL.md"}
    text = p["assets"][0]["skill_text"] if output is None else output
    d["messages"] += [dict(role="assistant", content=None, tool_calls=[dict(
        id="read1", type="function", function=dict(name=function, arguments=json.dumps(args)))]),
        dict(role="tool", tool_call_id="read1", content=text)]
    return d


class FileReadTests(unittest.TestCase):
    def test_cat_attaches_only_the_skill_returned_and_preserves_text(self):
        p = policy()
        d = file_result(p)
        out = inject(d, p)
        self.assertEqual(out["messages"][:-1], d["messages"])
        loads = validate_delivery(out, p)
        self.assertEqual([(x["skill"], x["trigger"]) for x in loads], [("alpha", "file_read")])
        self.assertEqual(len(images(out)), 1)
        self.assertNotIn(p["assets"][1]["body"], json.dumps(out))

    def test_loop_and_python_reads_are_matched_by_returned_content(self):
        p = policy()
        for command in ('for d in /root/.opencode/skills/*; do cat "$d/SKILL.md"; done',
                        "python3 /tmp/read_skill_files.py"):
            d = file_result(p, arguments={"command": command},
                            output="\n===\n".join(a["skill_text"] for a in p["assets"]))
            out = inject(d, p)
            self.assertEqual(len(images(out)), 2)
            self.assertEqual({x["skill"] for x in validate_delivery(out, p)}, {"alpha", "beta"})

    def test_numbered_file_reader(self):
        p = policy()
        raw = p["assets"][0]["skill_text"]
        for line_format in ("{i:05d}| {line}", "{i}: {line}", "{i}\t{line}", "L{i}: {line}"):
            output = "<file>\n" + "\n".join(line_format.format(i=i, line=line)
                      for i, line in enumerate(raw.splitlines(), 1)) + "\n</file>"
            d = file_result(p, function="read", arguments={"filePath": "/skills/alpha/SKILL.md"}, output=output)
            self.assertEqual(len(images(inject(d, p))), 1)

    def test_partial_read_requires_actual_prose_and_specific_skill(self):
        p = policy()
        asset = p["assets"][0]
        from protocol import digest, policy_id, skill_body
        asset["skill_text"] += "\nA source-specific paragraph for alpha that describes a detailed sequence of operations for this skill.\nAnother paragraph.\n"
        asset["body"] = skill_body(asset["skill_text"])
        asset["skill_sha256"] = digest(asset["skill_text"].encode())
        p["id"] = policy_id(p)
        fragment = asset["skill_text"].splitlines()[-2]
        good = file_result(p, function="read", arguments={"filePath": "/skills/alpha/SKILL.md", "offset": 8}, output="00009| " + fragment)
        loads = validate_delivery(inject(good, p), p)
        self.assertEqual(loads[0]["content_match"], "excerpt")
        bad = file_result(p, function="read", arguments={"filePath": "/skills/beta/SKILL.md"}, output=fragment)
        self.assertEqual(validate_delivery(inject(bad, p), p), [])

    def test_listing_failures_summaries_and_reference_reads_do_not_activate(self):
        p = policy()
        for output in ("/skills/alpha/SKILL.md\n/skills/beta/SKILL.md", "SKILL.md\nassets\nreferences",
                       "cat: /skills/alpha/SKILL.md: Permission denied", "[Old tool result content cleared]",
                       "[Tool execution was interrupted]", "Read alpha earlier; see /skills/alpha/SKILL.md", ""):
            d = file_result(p, output=output)
            self.assertIs(inject(d, p), d)
        reference = file_result(p, arguments={"command": "cat /skills/alpha/references/guide.md"}, output="# Reference\nAn independent reference file.")
        self.assertFalse(images(inject(reference, p)))

    def test_unrelated_write_output_and_user_quotes_do_not_activate(self):
        p = policy()
        d = file_result(p, function="write")
        self.assertIs(inject(d, p), d)
        d = request()
        d["messages"].append(dict(role="user", content=p["assets"][0]["skill_text"]))
        self.assertIs(inject(d, p), d)

    def test_multi_read_batch_attaches_after_all_results(self):
        p = policy()
        d = file_result(p)
        d["messages"][-2]["tool_calls"].append(dict(id="read2", type="function", function=dict(
            name="read", arguments=json.dumps({"filePath": "/skills/beta/SKILL.md"}))))
        d["messages"].append(dict(role="tool", tool_call_id="read2", content=p["assets"][1]["skill_text"]))
        out = inject(d, p)
        self.assertEqual(out["messages"][:-1], d["messages"])
        self.assertEqual(len(images(out)), 2)

    def test_repeated_reads_replay_one_figure_per_skill(self):
        p = policy()
        d = file_result(p)
        out = inject(d, p)
        self.assertEqual(inject(out, p), out)
        extra = copy.deepcopy(d["messages"][-2:])
        extra[0]["tool_calls"][0]["id"] = "read2"
        extra[1]["tool_call_id"] = "read2"
        d["messages"] += extra
        out = inject(d, p)
        self.assertEqual(len(images(out)), 1)
        self.assertEqual([x["image_attached"] for x in validate_delivery(out, p)], [True, False])
        compacted = copy.deepcopy(d)
        compacted["messages"][3]["content"] = "[Old tool result content cleared]"
        after = inject(compacted, p)
        self.assertEqual(len(images(after)), 1)
        self.assertEqual(validate_delivery(after, p)[0]["call_id"], "read2")

    def test_text_control_is_unchanged_but_records_multiple_skills_in_one_call(self):
        p = policy("text")
        d = file_result(p, output="\n".join(a["skill_text"] for a in p["assets"]))
        self.assertIs(inject(d, p), d)
        with tempfile.TemporaryDirectory() as directory:
            trial = Path(directory)
            (trial / "trajectory").mkdir()
            (trial / "trajectory/llm_trajectory.jsonl").write_text(json.dumps(dict(
                request=dict(body=d), response=dict(status_code=200))) + "\n")
            (trial / "result.json").write_text(json.dumps(dict(settings_sent=dict(main_calls=1))))
            report = audit_rollout(trial, p)
            self.assertTrue(report["valid"])
            self.assertEqual(report["activated_skills"], ["alpha", "beta"])
            self.assertEqual(len(report["activations"]), 2)


if __name__ == "__main__":
    unittest.main()
