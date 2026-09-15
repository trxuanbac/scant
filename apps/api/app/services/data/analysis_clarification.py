"""Shared response contract for analysis choices that require user input."""

from __future__ import annotations

from typing import Any, Literal


ClarificationKind = Literal["sheet", "column", "date", "unit"]
SUPPORTED_KINDS = {"sheet", "column", "date", "unit"}
SAFE_CONTEXT_KEYS = {
    "sheet",
    "sheets",
    "range",
    "ranges",
    "operation",
    "intent",
    "requested",
    "source_id",
    "source_version",
}


def _safe_context(context: dict[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (context or {}).items():
        if key not in SAFE_CONTEXT_KEYS:
            continue
        if value is None or isinstance(value, (str, int, float, bool)):
            safe[key] = value
        elif isinstance(value, (list, tuple)) and all(
            item is None or isinstance(item, (str, int, float, bool)) for item in value
        ):
            safe[key] = list(value)
    return safe


def _candidate(candidate: Any) -> dict[str, Any] | None:
    if isinstance(candidate, str):
        value = candidate.strip()
        return {"value": value, "label": value} if value else None
    if not isinstance(candidate, dict):
        return None
    value = candidate.get("value", candidate.get("name"))
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    item: dict[str, Any] = {"value": value, "label": str(candidate.get("label") or value)}
    confidence = candidate.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        item["confidence"] = round(max(0.0, min(float(confidence), 1.0)), 2)
    reason = candidate.get("reason")
    if isinstance(reason, str) and reason.strip():
        item["reason"] = reason.strip()
    return item


def build_clarification(
    kind: ClarificationKind,
    question: str,
    candidates: list[Any] | tuple[Any, ...],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind not in SUPPORTED_KINDS:
        raise ValueError("Unsupported clarification kind")
    clean_question = question.strip() if isinstance(question, str) else ""
    if not clean_question:
        raise ValueError("Clarification question is required")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_candidate in candidates:
        item = _candidate(raw_candidate)
        if item is None or item["value"] in seen:
            continue
        seen.add(item["value"])
        normalized.append(item)
    if not normalized:
        raise ValueError("Clarification candidates are required")
    safe_context = _safe_context(context)
    return {
        "status": "needs_clarification",
        "answer": clean_question,
        "clarification": {
            "kind": kind,
            "question": clean_question,
            "candidates": normalized,
            "context": safe_context,
        },
        "context": safe_context,
        "evidence": None,
        "result": {},
        "actions": [],
        "pending_actions": [],
        "status_steps": ["Cần bạn chọn trước khi tiếp tục."],
    }
