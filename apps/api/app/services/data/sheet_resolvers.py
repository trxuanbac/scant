from typing import Any, Dict, List, Optional, Tuple
import re
import unicodedata


def remove_diacritics(text: str) -> str:
    """Removes Vietnamese diacritics / accents for robust matching ('HN Chính T8' -> 'hn chinh t8')."""
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    cleaned = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r"\s+", " ", cleaned).strip().lower()


class AmbiguousSheetError(ValueError):
    def __init__(self, requested_sheet: str, candidates: List[str]):
        self.requested_sheet = requested_sheet
        self.candidates = candidates
        super().__init__(f"Ambiguous sheet {requested_sheet!r}: {', '.join(candidates)}")


def matching_sheet_candidates(requested_sheet: str, available_sheets: List[str]) -> List[str]:
    """Return all plausible matches; an explicit exact name takes precedence."""
    requested = requested_sheet.strip()
    if requested in available_sheets:
        return [requested]
    case_matches = [s for s in available_sheets if s.strip().lower() == requested.lower()]
    if case_matches:
        return case_matches
    normalized = remove_diacritics(requested)
    accent_matches = [s for s in available_sheets if remove_diacritics(s) == normalized]
    if accent_matches:
        return accent_matches
    tokens = set(normalized.split())
    candidates = []
    for sheet in available_sheets:
        sheet_norm = remove_diacritics(sheet)
        sheet_tokens = set(sheet_norm.split())
        if normalized and (normalized in sheet_norm or sheet_norm in normalized):
            candidates.append(sheet)
        elif tokens and (tokens.issubset(sheet_tokens) or sheet_tokens.issubset(tokens)):
            if min(len(tokens), len(sheet_tokens)) / max(len(tokens), len(sheet_tokens)) >= 0.5:
                candidates.append(sheet)
    return candidates


class SheetResolver:
    """
    Dedicated sheet resolver.
    Never treats generic column phrases (e.g. 'cột số quan trọng nhất') as sheets.
    Resolves against workbook actual sheets using diacritics-insensitive and token scoring.
    """

    @classmethod
    def _is_column_phrase(cls, candidate: str) -> bool:
        norm = remove_diacritics(candidate)
        return bool(re.match(r"^(cot|column|truong|field|dong|row|o|cell)\b", norm))

    @classmethod
    def extract_sheet_mention(cls, text: str, available_sheets: Optional[List[str]] = None) -> Optional[str]:
        if not text:
            return None

        # 1. Parentheses, e.g. (HN Chính T8) or (sheet HN Chính T8)
        match_paren = re.search(r"\((?:sheet\s+)?([^)]+)\)", text, flags=re.IGNORECASE)
        if match_paren:
            cand = match_paren.group(1).strip()
            if len(cand) >= 2 and not cand.startswith("http") and not cls._is_column_phrase(cand):
                return cand

        # 2. Quotes, e.g. 'HN Chính T8' or "HN Chính T8"
        match_quote = re.search(r"['\"](?:sheet\s+)?([^'\"]+)['\"]", text, flags=re.IGNORECASE)
        if match_quote:
            cand = match_quote.group(1).strip()
            if len(cand) >= 2 and not cand.startswith("http") and not cls._is_column_phrase(cand):
                return cand

        # 3. Explicit sheet markers ('ở sheet X', 'trong sheet X', 'sheet: X', 'chuyển sang X')
        match_kw = re.search(
            r"(?:ở\s+sheet|trong\s+sheet|tại\s+sheet|trên\s+sheet|sheet|worksheet|trang\s+tính|bang\s+tinh|bảng\s+tính)\s*[:=]?\s+([A-Za-z0-9_\u00C0-\u024F\u1EA0-\u1EF9\s]+?)(?=(?:,|\.|\?|!|\s+kiểm\s+tra|\s+xem|\s+từ|\s+so\s+sánh|\s+bôi\s+vàng|\s+tô\s+vàng|$))",
            text,
            flags=re.IGNORECASE,
        )
        if match_kw:
            cand = match_kw.group(1).strip()
            if len(cand) >= 2 and not cand.startswith("http") and not re.match(r"^[A-Za-z]+\d+$", cand) and not cls._is_column_phrase(cand):
                return cand

        # 4. Direct match against available sheets if provided
        if available_sheets:
            text_norm = remove_diacritics(text)
            for s in sorted(available_sheets, key=lambda x: len(x), reverse=True):
                s_norm = remove_diacritics(s)
                if s_norm and re.search(rf"\b{re.escape(s_norm)}\b", text_norm):
                    return s

        return None

    @classmethod
    def resolve_sheet(
        cls,
        text: Optional[str],
        default_sheet: str,
        available_sheets: List[str],
    ) -> Tuple[str, Optional[str]]:
        """
        Returns (resolved_sheet_name, sheet_mention_if_any).
        """
        if not available_sheets:
            return default_sheet or "Sheet1", None

        mention = cls.extract_sheet_mention(text or "", available_sheets)
        if mention:
            candidates = matching_sheet_candidates(mention, available_sheets)
            if len(candidates) > 1:
                raise AmbiguousSheetError(mention, candidates)
            if len(candidates) == 1:
                return candidates[0], mention
            mention_clean = mention.strip()
            # Exact
            if mention_clean in available_sheets:
                return mention_clean, mention
            # Case / Diacritics
            m_norm = remove_diacritics(mention_clean)
            for s in available_sheets:
                if remove_diacritics(s) == m_norm:
                    return s, mention
            # Token match
            m_tokens = set(m_norm.split())
            best_match = None
            best_score = 0.0
            for s in available_sheets:
                s_tokens = set(remove_diacritics(s).split())
                if m_tokens and (m_tokens == s_tokens or m_tokens.issubset(s_tokens)):
                    score = len(m_tokens) / max(len(s_tokens), 1)
                    if score > best_score:
                        best_score = score
                        best_match = s
            if best_match and best_score >= 0.5:
                return best_match, mention

        # Fallback to default active sheet if valid, otherwise first available sheet
        if default_sheet and default_sheet in available_sheets:
            return default_sheet, None
        for s in available_sheets:
            if remove_diacritics(s) == remove_diacritics(default_sheet or ""):
                return s, None

        return available_sheets[0], None


class ColumnResolver:
    """
    Dedicated column resolver.
    Handles semantic matching (e.g. 'thực lĩnh' -> 'Thực lĩnh', 'lương' -> 'Lương cơ bản'),
    diacritics, and confidence scoring.
    """

    SEMANTIC_SYNONYMS = {
        "luong": ["luong co ban", "thuc linh", "thu nhap", "salary", "gross salary", "net salary", "muc luong", "tong luong"],
        "thuc linh": ["thuc linh", "thuc nhan", "net salary", "net pay", "thuc linh thang", "tong thuc linh"],
        "doanh thu": ["doanh thu", "revenue", "sales", "tong doanh thu", "doanh so", "tien thu"],
        "chi phi": ["chi phi", "cost", "expense", "tong chi phi", "tien chi"],
        "so luong": ["so luong", "quantity", "qty", "count", "sl"],
        "ho ten": ["ho ten", "ho va ten", "ten nhan vien", "ten lai xe", "ho ten lai xe", "ten", "full name", "name"],
        "ma": ["ma nv", "ma nhan vien", "ma don", "ma code", "id", "employee id", "code"],
    }

    @classmethod
    def rank_candidates(
        cls,
        requested_column: str,
        columns_schema: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Rank plausible columns without discarding close alternatives."""
        if not columns_schema or not isinstance(requested_column, str):
            return []
        req_norm = remove_diacritics(requested_column).strip()
        if not req_norm:
            return []
        req_tokens = set(req_norm.split())
        ranked: List[Dict[str, Any]] = []
        semantic_terms: set[str] = set()
        for key, synonyms in cls.SEMANTIC_SYNONYMS.items():
            if req_norm == key or req_norm in synonyms:
                semantic_terms.update([key, *synonyms])

        for position, col in enumerate(columns_schema):
            col_name = str(col.get("name", "")).strip()
            col_norm = remove_diacritics(col_name)
            col_tokens = set(col_norm.split())
            confidence = 0.0
            reason = "Không đủ độ tin cậy"
            match_kind = "none"
            if col_name == requested_column:
                confidence, reason, match_kind = 1.0, "Khớp chính xác 100%", "exact"
            elif col_norm == req_norm:
                confidence = 0.95
                reason = f"Khớp không dấu: '{requested_column}' -> '{col_name}'"
                match_kind = "accent_exact"
            else:
                overlap = len(req_tokens & col_tokens)
                if req_tokens and col_tokens and (
                    req_tokens.issubset(col_tokens) or col_tokens.issubset(req_tokens)
                ):
                    confidence = min(len(req_tokens), len(col_tokens)) / max(
                        len(req_tokens), len(col_tokens)
                    )
                elif req_tokens and col_tokens:
                    confidence = overlap / max(len(req_tokens | col_tokens), 1)
                if confidence:
                    reason = (
                        f"Khớp từ khóa ({int(confidence * 100)}%): "
                        f"'{requested_column}' -> '{col_name}'"
                    )
                    match_kind = "token"
                if semantic_terms and any(term in col_norm for term in semantic_terms):
                    confidence = max(confidence, 0.85)
                    reason = f"Hiểu theo ngữ nghĩa '{requested_column}' là cột '{col_name}'"
                    match_kind = "semantic"
            ranked.append(
                {
                    "name": col_name,
                    "letter": col.get("letter", "A"),
                    "index": col.get("index", position + 1),
                    "header_row": col.get("header_row", 1),
                    "confidence": round(confidence, 2),
                    "reason": reason,
                    "match_kind": match_kind,
                    "_position": position,
                }
            )
        ranked.sort(key=lambda item: (-item["confidence"], item["_position"]))
        for item in ranked:
            item.pop("_position", None)
        return ranked

    @classmethod
    def resolve_column(
        cls,
        requested_column: str,
        columns_schema: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Resolve a column only when one supported candidate clearly wins."""
        if not columns_schema:
            return {
                "found": False,
                "ambiguous": False,
                "name": None,
                "letter": None,
                "confidence": 0.0,
                "reason": "No columns available",
                "candidates": [],
            }
        ranked = cls.rank_candidates(requested_column, columns_schema)
        supported = [candidate for candidate in ranked if candidate["confidence"] >= 0.4]
        if not supported:
            return {
                "found": False,
                "ambiguous": False,
                "name": None,
                "letter": None,
                "confidence": 0.0,
                "reason": f"Không tìm thấy cột phù hợp với '{requested_column}'",
                "candidates": [c.get("name") for c in columns_schema[:8]],
            }
        top = supported[0]
        exact = top["match_kind"] in {"exact", "accent_exact"}
        close = [
            candidate
            for candidate in supported
            if top["confidence"] - candidate["confidence"] <= 0.08
        ]
        if not exact and len(close) > 1:
            return {
                "found": False,
                "ambiguous": True,
                "name": None,
                "letter": None,
                "confidence": top["confidence"],
                "reason": "Có nhiều cột phù hợp với độ tin cậy gần nhau",
                "candidates": [candidate["name"] for candidate in close],
                "ranked_candidates": close,
            }
        return {"found": True, "ambiguous": False, **top}


sheet_resolver = SheetResolver()
column_resolver = ColumnResolver()
