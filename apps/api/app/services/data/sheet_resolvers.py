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
    def resolve_column(
        cls,
        requested_column: str,
        columns_schema: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Resolves requested column string against sheet's column schema.
        Returns detailed candidate, matched name, letter, index, confidence, and semantic reason.
        """
        if not columns_schema:
            return {"found": False, "name": None, "letter": None, "confidence": 0.0, "reason": "No columns available"}

        req_norm = remove_diacritics(requested_column).strip()
        req_tokens = set(req_norm.split())

        # 1. Exact match
        for col in columns_schema:
            col_name = str(col.get("name", "")).strip()
            if col_name == requested_column:
                return {
                    "found": True,
                    "name": col_name,
                    "letter": col.get("letter", "A"),
                    "index": col.get("index", 1),
                    "header_row": col.get("header_row", 1),
                    "confidence": 1.0,
                    "reason": "Khớp chính xác 100%",
                }

        # 2. Diacritics-insensitive match
        for col in columns_schema:
            col_name = str(col.get("name", "")).strip()
            if remove_diacritics(col_name) == req_norm:
                return {
                    "found": True,
                    "name": col_name,
                    "letter": col.get("letter", "A"),
                    "index": col.get("index", 1),
                    "header_row": col.get("header_row", 1),
                    "confidence": 0.95,
                    "reason": f"Khớp không dấu: '{requested_column}' -> '{col_name}'",
                }

        # 3. Substring / Token Containment
        best_col = None
        best_score = 0.0
        for col in columns_schema:
            col_name = str(col.get("name", "")).strip()
            c_norm = remove_diacritics(col_name)
            c_tokens = set(c_norm.split())
            if req_norm in c_norm or c_norm in req_norm:
                score = min(len(req_norm), len(c_norm)) / max(len(req_norm), len(c_norm))
            else:
                overlap = len(req_tokens & c_tokens)
                score = overlap / max(len(req_tokens | c_tokens), 1)
            if score > best_score:
                best_score = score
                best_col = col

        if best_col and best_score >= 0.4:
            return {
                "found": True,
                "name": best_col["name"],
                "letter": best_col.get("letter", "A"),
                "index": best_col.get("index", 1),
                "header_row": best_col.get("header_row", 1),
                "confidence": round(best_score, 2),
                "reason": f"Khớp từ khóa ({int(best_score * 100)}%): '{requested_column}' -> '{best_col['name']}'",
            }

        # 4. Semantic synonyms
        for key, syns in cls.SEMANTIC_SYNONYMS.items():
            if req_norm == key or req_norm in syns:
                for syn in syns:
                    for col in columns_schema:
                        col_name = str(col.get("name", "")).strip()
                        if syn in remove_diacritics(col_name):
                            return {
                                "found": True,
                                "name": col_name,
                                "letter": col.get("letter", "A"),
                                "index": col.get("index", 1),
                                "header_row": col.get("header_row", 1),
                                "confidence": 0.85,
                                "reason": f"Hiểu theo ngữ nghĩa '{requested_column}' là cột '{col_name}'",
                            }

        return {
            "found": False,
            "name": None,
            "letter": None,
            "confidence": 0.0,
            "reason": f"Không tìm thấy cột phù hợp với '{requested_column}'",
            "candidates": [c.get("name") for c in columns_schema[:8]],
        }


sheet_resolver = SheetResolver()
column_resolver = ColumnResolver()
