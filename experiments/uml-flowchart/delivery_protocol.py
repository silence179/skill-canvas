"""Strict, deterministic skill input delivery for the paired experiment.

This stdlib-only source is also appended to BenchFlow's private proxy callback.
Keep import-time work independent of the workspace and credentials.
"""

import base64
import copy
import hashlib
import json
import re


METHOD = "forced-prefix-v1"
MARKER = "[SkillCanvas forced skill inputs]"
SKILLS = ("pymatgen", "sympy")
HELPER_PREFIXES = (
    "You are a title generator.",
    "Summarize what was done in this conversation.",
    "You are an anchored context summarization assistant",
)


class SkillDeliveryError(Exception):
    """A deterministic rejection; LiteLLM returns 400, with no text fallback."""

    status_code = 400

    def __init__(self, reason):
        self.message = "experiment_fidelity/skill_delivery: " + reason
        super().__init__(self.message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def policy_id(policy):
    value = {k: v for k, v in policy.items() if k != "id"}
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def validate_policy(policy):
    if policy.get("method") != METHOD or policy.get("arm") not in {"text", "image"}:
        raise SkillDeliveryError("unsupported policy")
    if policy.get("id") != policy_id(policy):
        raise SkillDeliveryError("policy hash mismatch")
    assets = policy.get("assets")
    expected = policy.get("skill_names", list(SKILLS))
    if (not isinstance(expected, list) or not expected
            or any(not isinstance(x, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", x) for x in expected)
            or len(set(expected)) != len(expected)
            or not isinstance(assets, list)
            or any(not isinstance(x, dict) for x in assets)
            or [x.get("skill") for x in assets] != expected):
        raise SkillDeliveryError("expected the exact ordered task skill catalog")
    for asset in assets:
        text = asset.get("guide_text")
        if not isinstance(text, str) or digest(text.encode()) != asset.get("guide_sha256"):
            raise SkillDeliveryError("GUIDE hash mismatch")
        if policy["arm"] == "image":
            try:
                raw = base64.b64decode(asset["image_data"], validate=True)
            except (ValueError, KeyError, TypeError) as error:
                raise SkillDeliveryError("missing or malformed PNG") from error
            if not raw.startswith(b"\x89PNG\r\n\x1a\n") or digest(raw) != asset.get("image_sha256"):
                raise SkillDeliveryError("PNG hash mismatch")
        elif "image_data" in asset or "image_sha256" in asset:
            raise SkillDeliveryError("text arm must contain no figures")


def public_policy(policy):
    return {
        "method": policy["method"], "arm": policy["arm"], "id": policy["id"],
        "adapter_sha256": policy.get("adapter_sha256", {}),
        **{key: policy[key] for key in ("task", "skill_names", "study_sha256") if key in policy},
        "assets": [
            {k: v for k, v in item.items() if k not in {"guide_text", "image_data"}}
            for item in policy["assets"]
        ],
    }


def prefix_content(policy):
    parts = [{"type": "text", "text": (
        f"{MARKER}\npolicy={policy['id']}\n"
        "The experiment harness supplies the skill resources below before the task. "
        "Inspect all supplied figures, when present, before using the complete "
        "GUIDE.md texts that follow. The figures are supplements; the full guides "
        "are authoritative. All supplied images and guides are already in this "
        "model input; no separate skill activation or image-opening call is needed. "
        "Use adjacent scripts and references under /skills/<skill>/ when needed."
    )}]
    if policy["arm"] == "image":
        for item in policy["assets"]:
            parts.extend([
                {"type": "text", "text": f"Figure: {item['skill']}/assets/flowchart.png"},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + item["image_data"], "detail": "high",
                }},
            ])
    for item in policy["assets"]:
        parts.append({"type": "text", "text": (
            f"Complete skill: /skills/{item['skill']}/GUIDE.md\n"
            + item["guide_text"]
        )})
    return parts


def message_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(x.get("text", "") for x in content if isinstance(x, dict))
    return ""


def is_helper(data):
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        raise SkillDeliveryError("missing chat messages")
    system = "\n".join(
        message_text(x.get("content")) for x in messages
        if isinstance(x, dict) and x.get("role") == "system"
    ).lstrip()
    # Only the pinned OpenCode's known non-agent threads are exempt. Unknown
    # request shapes are rejected rather than silently classified as helpers.
    if system.startswith(HELPER_PREFIXES) and not data.get("tools"):
        return True
    if not isinstance(data.get("tools"), list) or not data["tools"]:
        raise SkillDeliveryError("unrecognized non-agent request")
    return False


def validate_delivery(data, policy):
    messages = data.get("messages") or []
    first_user = next((x for x in messages if x.get("role") == "user"), None)
    if first_user is None or first_user.get("content") != prefix_content(policy):
        raise SkillDeliveryError("figures/guides missing, altered, or out of order")


def inject(data, policy):
    if is_helper(data):
        return data
    # Proxy-owned metadata can hold tracing objects/locks. Copy only the JSON
    # conversation we change, preserving all original routing and auth objects.
    result = dict(data)
    messages = copy.deepcopy(data["messages"])
    result["messages"] = messages
    index = next((i for i, x in enumerate(messages) if x.get("role") == "user"), None)
    if index is None:
        raise SkillDeliveryError("task user message missing")
    expected = prefix_content(policy)
    if messages[index].get("content") != expected:
        messages.insert(index, {"role": "user", "content": expected})
    validate_delivery(result, policy)
    return result


def attach_logger_hook(logger_instance, policy):
    """Preserve BenchFlow's routing, budgets, capture and original guard."""
    validate_policy(policy)
    previous = logger_instance.async_pre_call_hook

    async def strict_pre_call(user_api_key_dict, cache, data, call_type):
        if call_type not in {"completion", "acompletion"}:
            raise SkillDeliveryError("this adapter requires chat completions")
        supplied = inject(data, policy)
        cleaned = await previous(user_api_key_dict, cache, supplied, call_type)
        forwarded = supplied if cleaned is None else cleaned
        if not is_helper(forwarded):
            validate_delivery(forwarded, policy)
        return forwarded

    logger_instance.async_pre_call_hook = strict_pre_call
