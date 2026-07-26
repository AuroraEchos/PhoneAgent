"""Conversation-context construction for the PhoneAgent model loop."""

from __future__ import annotations

import json
from typing import Any

from phoneagent.actions.compatibility import has_provider_coordinate_marker
from phoneagent.model.client import MessageBuilder


def append_observation_message(
    messages: list[dict[str, Any]],
    *,
    observation: Any,
    state: Any,
    system_prompt: str,
    user_prompt: str | None,
    is_first: bool,
    strict_recovery: str | None,
    app_context: dict[str, Any],
    notes: list[str],
    include_app_context: bool,
    app_context_char_budget: int,
) -> None:
    """Append one screenshot-backed user turn."""
    if is_first:
        messages.append(MessageBuilder.create_system_message(system_prompt))

    screen_payload = {
        **observation.to_screen_info(),
        "current_app": observation.current_app,
        "phase": state.phase.value,
        "stagnant_observation_count": state.stagnant_observation_count,
    }
    sections: list[str] = []
    goal = user_prompt or state.goal
    if goal:
        sections.append(f"** User Goal **\n{goal}")
    if strict_recovery:
        sections.append("** STRICT ACTION RECOVERY **\n" + strict_recovery)
    if not is_first:
        previous = build_previous_execution_info(state)
        if previous:
            sections.append(previous)
    if include_app_context and app_context:
        sections.append(
            "** Device App Context **\n"
            + serialize_app_context(app_context, app_context_char_budget)
        )
    if notes:
        sections.append(
            "** Saved Notes **\n"
            + json.dumps(notes[-20:], ensure_ascii=False, separators=(",", ":"))
        )
    sections.append(f"** Runtime Phase **\n{state.phase.value}")
    sections.append("** Screen Info **\n" + MessageBuilder.build_screen_info(**screen_payload))
    messages.append(
        MessageBuilder.create_user_message(
            text="\n\n".join(sections),
            image_base64=observation.screenshot.base64_data,
            image_mime_type=observation.screenshot.mime_type,
        )
    )


def serialize_app_context(context: dict[str, Any], budget: int) -> str:
    """Serialize task-relevant app context under a fixed character budget."""
    text = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= budget:
        return text
    minimal = {
        "catalog_available": context.get("catalog_available"),
        "installed_launchable_count": context.get("installed_launchable_count"),
        "likely_goal_apps": context.get("likely_goal_apps", [])[:1],
        "context_policy": "hard_truncated_to_primary_candidate",
        "launch_policy": context.get("launch_policy"),
    }
    compact = json.dumps(minimal, ensure_ascii=False, separators=(",", ":"))
    if len(compact) <= budget:
        return compact
    primary = primary_app_candidate(context) or {}
    return json.dumps(
        {
            "catalog_available": context.get("catalog_available"),
            "installed_launchable_count": context.get("installed_launchable_count"),
            "primary_candidate": {
                "label": primary.get("label"),
                "package_name": primary.get("package_name"),
            },
            "context_policy": "minimal_valid_json",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def prepare_protocol_recovery(
    messages: list[dict[str, Any]],
    *,
    reason: str,
    app_context: dict[str, Any],
    rejected_action: str | None = None,
) -> str:
    """Discard a malformed pending turn and prepare one strict retry message."""
    if messages and messages[-1].get("role") == "user":
        messages.pop()
    compact_for_protocol_recovery(messages)
    candidate = primary_app_candidate(app_context)
    candidate_text = ""
    if candidate:
        candidate_text = (
            "\nResolved app candidate:\n"
            f"- label: {candidate.get('label', '')}\n"
            f"- package: {candidate.get('package_name', '')}\n"
        )
    coordinate_hint = ""
    if has_provider_coordinate_marker(rejected_action):
        coordinate_hint = (
            "\nThe rejected action used a provider-specific coordinate marker. "
            "Do not emit <point>, <point_2d>, <box>, <bbox>, or special point tokens. "
            "Write coordinate arguments as bare numeric pairs, for example "
            'element=[250,126] or start=[500,800], end=[500,200].\n'
        )
    return (
        f"Previous model output was unusable: {reason}.\n"
        "Do not repeat prior reasoning or enumerate applications. "
        "Return exactly one valid action inside <answer>...</answer>."
        f"{coordinate_hint}"
        f"{candidate_text}"
        "Use the current screen and resolved candidate. Do not copy placeholder values."
    )


def compact_for_protocol_recovery(messages: list[dict[str, Any]]) -> None:
    """Keep the system message and most recent completed user/assistant pair."""
    if not messages:
        return
    system = messages[0] if messages[0].get("role") == "system" else None
    body = messages[1:] if system is not None else messages
    last_pair: list[dict[str, Any]] = []
    for index in range(len(body) - 2, -1, -1):
        if (
            body[index].get("role") == "user"
            and index + 1 < len(body)
            and body[index + 1].get("role") == "assistant"
        ):
            last_pair = [body[index], body[index + 1]]
            break
    messages[:] = ([system] if system is not None else []) + last_pair


def primary_app_candidate(context: dict[str, Any]) -> dict[str, Any] | None:
    likely = context.get("likely_goal_apps", [])
    if not isinstance(likely, list) or not likely or not isinstance(likely[0], dict):
        return None
    resolution = likely[0].get("resolution", {})
    matched = resolution.get("matched_app") if isinstance(resolution, dict) else None
    if isinstance(matched, dict):
        return matched
    candidates = likely[0].get("candidates", [])
    if candidates and isinstance(candidates[0], dict):
        app = candidates[0].get("app")
        return app if isinstance(app, dict) else None
    return None


def build_previous_execution_info(state: Any) -> str:
    previous = state.last_execution
    if not previous:
        return ""
    payload = {
        "success": previous.get("success"),
        "command_success": previous.get("command_success"),
        "should_finish": previous.get("should_finish"),
        "message": previous.get("message"),
        "error_code": previous.get("error_code"),
        "action": previous.get("action"),
        "verification": previous.get("verification"),
        "recovery": previous.get("recovery"),
        "stagnant_observation_count": state.stagnant_observation_count,
    }
    return "** Previous Action Result **\n" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


def trim_context(messages: list[dict[str, Any]], turns: int) -> None:
    """Retain the system message, recent completed turns and current user turn."""
    if len(messages) <= 2:
        return
    system = messages[0]
    body = messages[1:]
    current_user = body[-1] if body and body[-1].get("role") == "user" else None
    completed = body[:-1] if current_user is not None else body
    pairs: list[list[dict[str, Any]]] = []
    index = 0
    while index + 1 < len(completed):
        first, second = completed[index], completed[index + 1]
        if first.get("role") == "user" and second.get("role") == "assistant":
            pairs.append([first, second])
            index += 2
        else:
            index += 1
    new_context = [system]
    for pair in pairs[-turns:]:
        new_context.extend(pair)
    if current_user is not None:
        new_context.append(current_user)
    messages[:] = new_context
