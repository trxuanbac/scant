"""Versioned source, scope, and evidence contracts for workbook analysis."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.services.data.sheet_resolvers import matching_sheet_candidates


SourceKind = Literal["stored_file", "upload", "linked"]
ScopeMode = Literal["workbook", "sheets", "sheet", "range"]


class AnalysisScopeError(ValueError):
    """The requested analysis scope cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class SourceVersion:
    source_id: str
    source_kind: SourceKind
    version: str
    display_name: str
    mime_type: str
    size_bytes: int

    def __post_init__(self) -> None:
        if self.source_kind not in {"stored_file", "upload", "linked"}:
            raise ValueError("Unsupported source kind")
        if not re.fullmatch(r"[a-f0-9]{64}", self.version):
            raise ValueError("Source version must be a lowercase SHA-256")
        if not self.source_id or not self.display_name or self.size_bytes < 0:
            raise ValueError("Source identity is incomplete")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AnalysisScope:
    mode: ScopeMode
    sheets: tuple[str, ...]
    cell_range: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "sheets": list(self.sheets), "range": self.cell_range}

    def as_legacy_dict(self) -> dict[str, Any]:
        if self.mode == "workbook":
            return {"type": "workbook"}
        if self.mode == "sheets":
            return {"type": "sheets", "sheets": list(self.sheets)}
        if self.mode == "range":
            return {"type": "sheet", "sheet": self.sheets[0], "range": self.cell_range}
        return {"type": "sheet", "sheet": self.sheets[0]}


def _resolve_sheet(requested: Any, available_sheets: list[str]) -> str:
    if not isinstance(requested, str) or not requested.strip():
        raise AnalysisScopeError("Tên sheet không hợp lệ.")
    candidates = matching_sheet_candidates(requested, available_sheets)
    if len(candidates) > 1:
        raise AnalysisScopeError(f"Tên sheet '{requested}' chưa rõ ràng.")
    if not candidates:
        raise AnalysisScopeError(f"Không tìm thấy sheet '{requested}'.")
    return candidates[0]


def _column_number(letters: str) -> int:
    value = 0
    for char in letters:
        value = value * 26 + ord(char) - 64
    return value


def _cell_coordinate(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", value)
    if not match:
        raise AnalysisScopeError("Vùng ô phải dùng địa chỉ A1 hợp lệ.")
    column = _column_number(match[1])
    row = int(match[2])
    if column > 16_384 or row > 1_048_576:
        raise AnalysisScopeError("Vùng ô vượt giới hạn Excel.")
    return column, row


def _normalize_range(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnalysisScopeError("Vùng ô không được để trống.")
    normalized = value.strip().upper().replace("$", "")
    parts = normalized.split(":")
    if len(parts) > 2:
        raise AnalysisScopeError("Vùng ô phải dùng địa chỉ A1 hợp lệ.")
    start = _cell_coordinate(parts[0])
    end = _cell_coordinate(parts[-1])
    if start[0] > end[0] or start[1] > end[1]:
        raise AnalysisScopeError("Điểm đầu của vùng ô phải đứng trước điểm cuối.")
    return normalized


def _parse_scope(raw_scope: Any) -> dict[str, Any] | None:
    if raw_scope in (None, ""):
        return None
    if isinstance(raw_scope, str):
        try:
            raw_scope = json.loads(raw_scope)
        except json.JSONDecodeError as exc:
            raise AnalysisScopeError("Scope phân tích không phải JSON hợp lệ.") from exc
    if not isinstance(raw_scope, dict):
        raise AnalysisScopeError("Scope phân tích phải là một object.")
    return raw_scope


def normalize_analysis_scope(
    raw_scope: Any,
    *,
    available_sheets: list[str],
    sheet_name: str | None = None,
    selected_range: str | None = None,
) -> AnalysisScope:
    if not available_sheets:
        raise AnalysisScopeError("Workbook không có sheet để phân tích.")

    parsed = _parse_scope(raw_scope)
    if parsed is None:
        if selected_range:
            resolved = _resolve_sheet(sheet_name, available_sheets)
            return AnalysisScope("range", (resolved,), _normalize_range(selected_range))
        if sheet_name:
            return AnalysisScope("sheet", (_resolve_sheet(sheet_name, available_sheets),))
        return AnalysisScope("workbook", tuple(available_sheets))

    mode = parsed.get("type")
    allowed_keys = {
        "workbook": {"type"},
        "sheets": {"type", "sheets"},
        "sheet": {"type", "sheet"},
        "range": {"type", "sheet", "range"},
    }
    if mode not in allowed_keys or set(parsed) != allowed_keys[mode]:
        raise AnalysisScopeError("Scope phân tích có trường hoặc loại không được hỗ trợ.")

    if mode == "workbook":
        return AnalysisScope("workbook", tuple(available_sheets))
    if mode == "sheets":
        requested = parsed["sheets"]
        if not isinstance(requested, list) or not requested:
            raise AnalysisScopeError("Cần chọn ít nhất một sheet.")
        resolved = tuple(_resolve_sheet(item, available_sheets) for item in requested)
        if len(set(resolved)) != len(resolved):
            raise AnalysisScopeError("Danh sách sheet không được trùng lặp.")
        return AnalysisScope("sheets", resolved)
    resolved = _resolve_sheet(parsed["sheet"], available_sheets)
    if mode == "range":
        return AnalysisScope("range", (resolved,), _normalize_range(parsed["range"]))
    return AnalysisScope("sheet", (resolved,))


def bind_analysis_evidence(
    payload: dict[str, Any],
    *,
    source_version: SourceVersion,
    scope: AnalysisScope,
) -> dict[str, Any]:
    bound = copy.deepcopy(payload)
    source_dict = source_version.as_dict()
    scope_dict = scope.as_dict()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidence" and isinstance(child, dict):
                    child["source_version"] = copy.deepcopy(source_dict)
                    child["scope"] = copy.deepcopy(scope_dict)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(bound)
    bound["analysis_context"] = {"source_version": source_dict, "scope": scope_dict}
    return bound
