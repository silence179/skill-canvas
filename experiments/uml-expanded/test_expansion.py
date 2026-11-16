"""Guards the 2026-11-14 expansion from fixed two-skill delivery to task catalogs."""

import copy
import sys
import unittest

from study import HERE, ROOT, TASKS, verify_study
sys.path.insert(0, str(HERE.parent / "uml-flowchart"))
from delivery_protocol import SkillDeliveryError, inject, policy_id, prefix_content, validate_delivery, validate_policy
from delivery_runner import load_policy


class ExpansionTests(unittest.TestCase):
    def test_all_thirteen_skills_have_balanced_complete_inputs(self):
        count = 0
        for task in TASKS:
            study = HERE / "tasks" / task
            manifest = verify_study(study)
            text = load_policy("text", study / "bundles/text")
            image = load_policy("image", study / "bundles/image")
            n = len(manifest["skills"])
            self.assertEqual(len(image["assets"]), n)
            self.assertEqual(sum(x["type"] == "image_url" for x in prefix_content(image)), n)
            self.assertEqual(prefix_content(text)[-n:], prefix_content(image)[-n:])
            self.assertEqual(image["task"], task)
            for skill in manifest["skills"]:
                source = ROOT / "repos/skillsbench/tasks" / task / "environment/skills" / skill
                self.assertEqual((source / "SKILL.md").read_bytes(),
                    (study / "bundles/image" / skill / "GUIDE.md").read_bytes())
            count += n
        self.assertEqual(count, 13)

    def test_rehashed_catalog_with_missing_duplicate_or_unknown_asset_is_rejected(self):
        policy = load_policy("image", HERE / "tasks/energy-market-pricing/bundles/image")
        for mutation in ("missing", "duplicate", "reorder"):
            value = copy.deepcopy(policy)
            if mutation == "missing":
                value["assets"].pop()
            elif mutation == "duplicate":
                value["skill_names"][1] = value["skill_names"][0]
            else:
                value["assets"].reverse()
            value["id"] = policy_id(value)
            with self.assertRaises(SkillDeliveryError):
                validate_policy(value)

    def test_four_figure_request_cannot_lose_one_figure(self):
        policy = load_policy("image", HERE / "tasks/r2r-mpc-control/bundles/image")
        request = {"messages": [{"role": "user", "content": "unchanged task"}], "tools": [{"type": "function"}]}
        result = inject(request, policy)
        validate_delivery(result, policy)
        result["messages"][0]["content"].pop(2)
        with self.assertRaises(SkillDeliveryError):
            validate_delivery(result, policy)


if __name__ == "__main__":
    unittest.main()
