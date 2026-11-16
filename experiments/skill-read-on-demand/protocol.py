"""SkillCanvas skill-read-on-demand-v2: media follows actual SKILL.md reads.

The proxy projects a media message after the matching tool-result batch. Native
tool text, task messages, tool definitions, and ordinary agent history are kept.
This module is stdlib-only; its source also runs in BenchFlow's proxy callback.
"""
import base64
import copy
import hashlib
import json
import re

METHOD = "skill-read-on-demand-v2"
MARKER = "[SkillCanvas read-triggered skill media]"
LEGACY_MARKER = "[SkillCanvas forced skill inputs]"
HELPERS = (
    "You are a title generator.",
    "Summarize what was done in this conversation.",
    "You are an anchored context summarization assistant",
)
FILE_TOOLS = {"read", "read_file", "readfile", "bash", "shell", "execute", "exec_command"}


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
              "\nFigures accompanying the SKILL.md content returned by the completed tools below. "
              "Use each figure with that skill's preceding text; the original tool output is preserved."}]
    assets = {a["skill"]: a for a in policy["assets"]}
    for load in loads:
        a = assets[load["skill"]]
        parts += [{"type": "text", "text": f"skill={a['skill']} tool_call_id={load['call_id']}"},
                  {"type": "image_url", "image_url": {
                      "url": "data:image/png;base64," + a["image_data"], "detail": "high"}}]
    return {"role": "user", "content": parts}


def parsed_arguments(function):
    args = function.get("arguments", {})
    try:
        args = json.loads(args) if isinstance(args, str) else args
    except (ValueError, TypeError):
        return {}
    return args if isinstance(args, dict) else {}


def content_views(text):
    """Keep raw output and also recognize the line numbers of ordinary readers."""
    views = [text]
    for pattern in (r"(?m)^\s*\d+\| ?", r"(?m)^\s*\d+: ?", r"(?m)^\s*\d+\t", r"(?m)^L\d+: ?"):
        if re.search(pattern, text):
            views.append(re.sub(pattern, "", text))
    return views


def body_excerpt_observed(body, views):
    """Require actual source prose, never merely a filename or directory entry."""
    lines = body.splitlines()
    fragments = [line for line in lines if len(line.strip()) >= 80]
    fragments += ["\n".join(lines[i:i + 3]) for i in range(max(0, len(lines) - 2))
                  if len("\n".join(lines[i:i + 3]).strip()) >= 80]
    return any(fragment in view for fragment in fragments for view in views)


def observed_file_reads(function, text, catalog, *, body_transform=None):
    """Associate returned source content with a registered skill, including cat loops.

    Full-source identity supports shell variables, loops and Python reads without
    interpreting shell code. Partial reads additionally require a concrete skill
    path and a source excerpt. Merely mentioning a path does not activate a skill.
    """
    if function.get("name", "").lower() not in FILE_TOOLS:
        return []
    views = content_views(text)
    args = parsed_arguments(function)
    explicit = "\n".join(str(args[k]) for k in ("filePath", "file_path", "path", "command", "cmd") if k in args)
    matches = []
    for name, asset in catalog.items():
        source, body = asset["skill_text"], asset["body"]
        if body_transform:
            source, body = body_transform(source), body_transform(body)
        complete = any(source.strip() in view or body in view for view in views)
        path = re.search(r"(?:^|[/\\])" + re.escape(name) + r"/SKILL\.md(?:$|[\s\"'`;|)])", explicit)
        partial = bool(path) and body_excerpt_observed(body, views)
        if complete or partial:
            matches.append(dict(skill=name, trigger="file_read", tool=function["name"],
                                content_match="complete" if complete else "excerpt"))
    return matches


def project(data, policy, *, body_transform=None):
    """Compute expected outbound messages and activation receipts without state.

    Match native skill loads or observed source text returned by file/shell tools.
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
    calls, pending, batch_loads, seen_skills = {}, set(), [], set()
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
        found = []
        if match and (not function or function.get("name") == "skill"):
            if not function or cid not in pending:
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
            found = [dict(skill=name, trigger="native_skill", tool="skill", content_match="complete")]
        elif function and function.get("name") == "skill":
            # Native errors do not activate skills. Unknown non-error formats
            # must not silently turn an image condition into text-only delivery.
            cleared = text.strip() in ("[Old tool result content cleared]", "[Tool execution was interrupted]")
            invalid_args = text.startswith("The skill tool was called with invalid arguments:")
            if not (cleared or invalid_args or re.match(r"\s*(?:Error\b|Tool execution (?:failed|aborted)\b|Permission\b)", text, re.I)):
                raise SkillDeliveryError("unrecognized native skill result format")
        elif function and cid in pending:
            found = observed_file_reads(function, text, catalog, body_transform=body_transform)
        for observation in found:
            name = observation["skill"]
            fresh = name not in seen_skills
            load = dict(observation, call_id=cid, tool_result_index=i,
                        image_attached=policy["arm"] == "image" and fresh)
            loads.append(load)
            if fresh:
                batch_loads.append(load)
                seen_skills.add(name)
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
