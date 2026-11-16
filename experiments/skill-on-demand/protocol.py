"""SkillCanvas skill-on-demand-v1: media follows successful native skill loads.

The proxy projects a media message after the matching tool-result batch. Native
tool text, task messages, tool definitions, and ordinary agent history are kept.
This module is stdlib-only; its source also runs in BenchFlow's proxy callback.
"""
import base64
import copy
import hashlib
import json
import re

METHOD = "skill-on-demand-v1"
MARKER = "[SkillCanvas on-demand skill media]"
LEGACY_MARKER = "[SkillCanvas forced skill inputs]"
HELPERS = (
    "You are a title generator.",
    "Summarize what was done in this conversation.",
    "You are an anchored context summarization assistant",
)


class SkillDeliveryError(Exception):
    status_code = 400

    def __init__(self, reason):
        self.message = "experiment_fidelity/skill_on_demand: " + reason
        super().__init__(self.message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def policy_id(policy):
    data = {k: v for k, v in policy.items() if k != "id"}
    return digest(json.dumps(data, sort_keys=True, ensure_ascii=False).encode())


def skill_body(text):
    front = re.match(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not front:
        raise SkillDeliveryError("SKILL.md frontmatter is missing")
    return text[front.end():].strip()


def validate_policy(policy):
    if policy.get("method") != METHOD or policy.get("arm") not in ("text", "image"):
        raise SkillDeliveryError("unsupported policy")
    if policy.get("id") != policy_id(policy):
        raise SkillDeliveryError("policy hash mismatch")
    assets = policy.get("assets")
    if not isinstance(assets, list) or not assets:
        raise SkillDeliveryError("empty skill catalog")
    names = set()
    for a in assets:
        name = a.get("skill")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or name in names:
            raise SkillDeliveryError("invalid or duplicate skill name")
        names.add(name)
        text = a.get("skill_text")
        if not isinstance(text, str) or digest(text.encode()) != a.get("skill_sha256"):
            raise SkillDeliveryError("SKILL.md hash mismatch")
        if skill_body(text) != a.get("body"):
            raise SkillDeliveryError("native skill body mismatch")
        if policy["arm"] == "image":
            try:
                raw = base64.b64decode(a["image_data"], validate=True)
            except (ValueError, KeyError, TypeError) as e:
                raise SkillDeliveryError("invalid PNG") from e
            if not raw.startswith(b"\x89PNG\r\n\x1a\n") or digest(raw) != a.get("image_sha256"):
                raise SkillDeliveryError("PNG hash mismatch")
        elif "image_data" in a or "image_sha256" in a:
            raise SkillDeliveryError("text arm must not contain media")


def public_policy(policy):
    return {k: v for k, v in policy.items() if k != "assets"} | {
        "assets": [{k: v for k, v in a.items() if k not in ("skill_text", "body", "image_data")}
                   for a in policy["assets"]]}


def message_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def is_helper(data):
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        raise SkillDeliveryError("missing chat messages")
    system = "\n".join(message_text(m.get("content")) for m in messages if m.get("role") == "system").lstrip()
    return system.startswith(HELPERS) and not data.get("tools")


def media_message(policy, loads):
    parts = [{"type": "text", "text": MARKER + "\npolicy=" + policy["id"] +
              "\nMedia returned with the completed skill calls below. Their original "
              "SKILL.md bodies are in the preceding tool results; figures supplement those bodies."}]
    assets = {a["skill"]: a for a in policy["assets"]}
    for load in loads:
        a = assets[load["skill"]]
        parts += [{"type": "text", "text": f"skill={a['skill']} tool_call_id={load['call_id']}"},
                  {"type": "image_url", "image_url": {
                      "url": "data:image/png;base64," + a["image_data"], "detail": "high"}}]
    return {"role": "user", "content": parts}


def project(data, policy, *, body_transform=None):
    """Compute expected outbound messages and activation receipts without state.

    Match a *successful* native result to its actual assistant skill tool call.
    Never insert between an assistant's parallel tool calls and their results.
    Reconstruct one historical media attachment per call rather than accumulating
    a fresh copy on each round. Compaction naturally drops absent tool results.
    """
    catalog = {a["skill"]: a for a in policy["assets"]}
    source = []
    for m in data["messages"]:
        text = message_text(m.get("content"))
        if m.get("role") == "user" and text.startswith(LEGACY_MARKER):
            raise SkillDeliveryError("legacy forced-prefix materials are forbidden")
        if m.get("role") == "user" and text.startswith(MARKER):
            continue  # checked against exact expected placement/content below
        source.append(m)
    result, loads = [], []
    calls, pending, batch_loads = {}, set(), []
    for i, m in enumerate(source):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            if pending:
                raise SkillDeliveryError("new assistant tool batch before previous results")
            for call in m["tool_calls"]:
                cid = call.get("id")
                if not cid or cid in calls:
                    raise SkillDeliveryError("missing or duplicate tool call id")
                function = call.get("function", {})
                calls[cid] = function
                pending.add(cid)
        result.append(m)
        if m.get("role") != "tool":
            continue
        cid = m.get("tool_call_id")
        function = calls.get(cid)
        text = message_text(m.get("content"))
        match = re.search(r'<skill_content name="([^"\n]+)">', text)
        if match:
            if not function or function.get("name") != "skill" or cid not in pending:
                raise SkillDeliveryError("skill result has no matching native skill call")
            args = function.get("arguments", {})
            try:
                args = json.loads(args) if isinstance(args, str) else args
                name = args["name"]
            except (ValueError, TypeError, KeyError) as e:
                raise SkillDeliveryError("invalid native skill arguments") from e
            if name != match.group(1) or name not in catalog:
                raise SkillDeliveryError("result skill name does not match registered call")
            expected = catalog[name]["body"]
            if body_transform:
                expected = body_transform(expected)
            if expected not in text or f"# Skill: {name}" not in text or "</skill_content>" not in text:
                raise SkillDeliveryError("original SKILL.md body missing or altered")
            load = {"skill": name, "call_id": cid, "tool_result_index": i}
            loads.append(load)
            batch_loads.append(load)
        elif function and function.get("name") == "skill":
            # Native errors do not activate skills. Unknown non-error formats
            # must not silently turn an image condition into text-only delivery.
            cleared = text.strip() in ("[Old tool result content cleared]", "[Tool execution was interrupted]")
            invalid_args = text.startswith("The skill tool was called with invalid arguments:")
            if not (cleared or invalid_args or re.match(r"\s*(?:Error\b|Tool execution (?:failed|aborted)\b|Permission\b)", text, re.I)):
                raise SkillDeliveryError("unrecognized native skill result format")
        pending.discard(cid)
        if not pending and batch_loads:
            if policy["arm"] == "image":
                result.append(media_message(policy, batch_loads))
            batch_loads = []
    if batch_loads:
        raise SkillDeliveryError("incomplete tool-result batch")
    return result, loads


def inject(data, policy):
    if is_helper(data):
        return data
    expected, _ = project(data, policy)
    # A supplied marker must already be authentic; do not silently repair a
    # changed media payload or misplaced/extra attachment in a recorded request.
    if any(m.get("role") == "user" and message_text(m.get("content")).startswith(MARKER)
           for m in data["messages"]) and data["messages"] != expected:
        raise SkillDeliveryError("existing skill media is changed, duplicated or misplaced")
    if data["messages"] == expected:
        return data
    result = dict(data)
    result["messages"] = copy.deepcopy(expected)
    return result


def validate_delivery(data, policy, *, body_transform=None):
    if is_helper(data):
        return []
    expected, loads = project(data, policy, body_transform=body_transform)
    if data["messages"] != expected:
        raise SkillDeliveryError("skill media missing or not linked to completed tool result")
    return loads


def attach_logger_hook(logger, policy):
    validate_policy(policy)
    previous = logger.async_pre_call_hook

    async def hook(user_api_key_dict, cache, data, call_type):
        if call_type not in ("completion", "acompletion"):
            raise SkillDeliveryError("chat completions required")
        forwarded = inject(data, policy)
        cleaned = await previous(user_api_key_dict, cache, forwarded, call_type)
        result = forwarded if cleaned is None else cleaned
        validate_delivery(result, policy)
        return result

    logger.async_pre_call_hook = hook
