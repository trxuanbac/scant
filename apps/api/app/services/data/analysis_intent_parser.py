from typing import Any, Dict, List, Optional, Tuple
import re
from app.services.data.sheet_resolvers import remove_diacritics, sheet_resolver, column_resolver


COLOR_MAP = {
    "vang": "#FEF08A",        # Yellow
    "vàng": "#FEF08A",
    "yellow": "#FEF08A",
    "do": "#FECACA",          # Red
    "đỏ": "#FECACA",
    "red": "#FECACA",
    "xanh la": "#BBF7D0",     # Green
    "xanh lá": "#BBF7D0",
    "xanh cay": "#BBF7D0",
    "green": "#BBF7D0",
    "xanh duong": "#BFDBFE",  # Blue
    "xanh dương": "#BFDBFE",
    "xanh bien": "#BFDBFE",
    "blue": "#BFDBFE",
    "cam": "#FED7AA",         # Orange
    "orange": "#FED7AA",
    "tim": "#E9D5FF",         # Purple
    "tím": "#E9D5FF",
    "purple": "#E9D5FF",
    "hong": "#FBCFE8",        # Pink
    "hồng": "#FBCFE8",
    "pink": "#FBCFE8",
    "xam": "#E2E8F0",         # Gray
    "xám": "#E2E8F0",
    "gray": "#E2E8F0",
}


class AnalysisIntentParser:
    """
    Structured Intent Parser for Spreadsheet Natural Language Analysis Requests.
    Accurately maps Vietnamese & English prompts to execution intents and tool parameters.
    """

    @classmethod
    def extract_color_from_text(cls, text: str) -> Optional[str]:
        norm = remove_diacritics(text)
        for key, hex_code in COLOR_MAP.items():
            key_norm = remove_diacritics(key)
            if re.search(rf"\b(to|boi|highlight|danh dau|mau)\s+{re.escape(key_norm)}\b", norm) or re.search(rf"\b{re.escape(key_norm)}\b", norm):
                if any(m in norm for m in ["to", "boi", "mau", "highlight", "danh dau"]):
                    return hex_code
        return None

    @classmethod
    def extract_target_type(cls, text: str) -> str:
        """Determines whether highlight / action targets 'cell', 'row', or 'range'."""
        norm = remove_diacritics(text)
        if any(w in norm for w in ["cac dong", "cac hang", "dong chua", "hang chua", "nguoi co", "nguoi do", "nhan vien do", "dong do"]):
            return "row"
        if any(w in norm for w in ["vung", "khoi", "range", "cot"]):
            return "range"
        return "cell"

    @classmethod
    def parse(
        cls,
        prompt: str,
        available_sheets: Optional[List[str]] = None,
        default_sheet: str = "Sheet1",
        ui_highlight_color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parses user analysis request into structured execution intent.
        """
        prompt_norm = remove_diacritics(prompt).strip()

        # 1. Resolve sheet mention
        resolved_sheet, sheet_mention = sheet_resolver.resolve_sheet(
            text=prompt,
            default_sheet=default_sheet,
            available_sheets=available_sheets or [default_sheet],
        )

        # 2. Extract highlight color & target type
        color_in_text = cls.extract_color_from_text(prompt)
        effective_color = color_in_text or ui_highlight_color or "#FEF08A"
        has_highlight_directive = bool(color_in_text or any(w in prompt_norm for w in ["to mau", "boi mau", "to vang", "boi vang", "to do", "highlight", "danh dau"]))
        target_type = cls.extract_target_type(prompt)

        # 3. Intent Detection Rules

        # A. CLEAR HIGHLIGHT
        if any(w in prompt_norm for w in ["xoa mau", "xoa highlight", "bo highlight", "bo danh dau", "clear highlight", "clear mau"]):
            return {
                "intent": "CLEAR_HIGHLIGHT",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "target_type": target_type,
                "color": None,
                "confidence": 1.0,
                "metric": None,
                "subject": None,
            }

        # B. AVERAGE (Evaluated before duplicates to avoid 'trung binh' collision)
        if any(w in prompt_norm for w in ["trung binh", "binh quan", "avg", "average", "mean"]):
            col_mention = cls._extract_candidate_metric(prompt_norm, ["trung binh", "binh quan", "avg", "average", "mean"])
            return {
                "intent": "AVERAGE",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "column_mention": col_mention,
                "target_type": target_type,
                "confidence": 0.95,
                "metric": col_mention,
                "subject": "trung bình",
            }

        # C. DUPLICATES
        is_dup_kw = bool(re.search(r"\b(trung\s+lap|duplicate|lap\s+lai|lap\s+du\s+lieu|giao\s+nhau|trung\s+nhau|bi\s+trung|du\s+lieu\s+trung|o\s+trung|cac\s+o\s+trung)\b", prompt_norm)) or ("trung" in prompt_norm and not any(k in prompt_norm for k in ["trung binh", "trung tam", "tap trung"]))
        if is_dup_kw and not any(w in prompt_norm for w in ["xoa mau", "xoa highlight"]):
            return {
                "intent": "FIND_DUPLICATES",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "target_type": target_type,
                "color": effective_color if has_highlight_directive else None,
                "has_highlight": has_highlight_directive,
                "confidence": 0.95,
                "metric": None,
                "subject": "dữ liệu trùng",
            }

        # C. BLANKS / MISSING CELLS
        if any(w in prompt_norm for w in ["o trong", "o thieu", "thieu du lieu", "blank", "missing", "chua nhap", "null", "rong"]):
            return {
                "intent": "FIND_BLANKS",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "target_type": target_type,
                "color": effective_color if has_highlight_directive else "#FED7AA",
                "has_highlight": has_highlight_directive,
                "confidence": 0.95,
                "metric": None,
                "subject": "ô trống",
            }

        # D. OUTLIERS / ANOMALIES (Explicit only!)
        if any(w in prompt_norm for w in ["bat thuong", "di thuong", "di biet", "outlier", "anomal"]):
            return {
                "intent": "DETECT_OUTLIERS",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "target_type": target_type,
                "color": effective_color if has_highlight_directive else "#FECACA",
                "has_highlight": has_highlight_directive,
                "confidence": 0.95,
                "metric": None,
                "subject": "điểm bất thường",
            }

        # E. CROSS-SHEET / COMPARE SHEETS
        if any(w in prompt_norm for w in ["so sanh 2 sheet", "so sanh hai sheet", "khop bang chi tiet", "khop voi bang", "doi chieu sheet", "kiem tra bang tong hop"]):
            return {
                "intent": "CROSS_SHEET_COMPARE",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "target_type": target_type,
                "confidence": 0.9,
                "metric": None,
                "subject": "đối chiếu sheet",
            }

        # F. FIND_MAX
        if any(w in prompt_norm for w in ["cao nhat", "lon nhat", "nhieu nhat", "max", "top 1 cao", "hang dau"]):
            # Extract possible column mention
            col_mention = cls._extract_candidate_metric(prompt_norm, ["cao nhat", "lon nhat", "nhieu nhat", "max"])
            return {
                "intent": "FIND_MAX",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "column_mention": col_mention,
                "target_type": target_type,
                "color": effective_color,
                "has_highlight": has_highlight_directive,
                "confidence": 0.95,
                "metric": col_mention,
                "subject": "giá trị cao nhất",
            }

        # G. FIND_MIN
        if any(w in prompt_norm for w in ["thap nhat", "nho nhat", "it nhat", "min", "bottom 1"]):
            col_mention = cls._extract_candidate_metric(prompt_norm, ["thap nhat", "nho nhat", "it nhat", "min"])
            return {
                "intent": "FIND_MIN",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "column_mention": col_mention,
                "target_type": target_type,
                "color": effective_color if has_highlight_directive else "#FED7AA",
                "has_highlight": has_highlight_directive,
                "confidence": 0.95,
                "metric": col_mention,
                "subject": "giá trị thấp nhất",
            }

        # H. SUM
        if any(w in prompt_norm for w in ["tong", "tong cong", "tong so", "sum", "total"]):
            col_mention = cls._extract_candidate_metric(prompt_norm, ["tong cong", "tong so", "tong", "sum", "total"])
            return {
                "intent": "SUM",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "column_mention": col_mention,
                "target_type": target_type,
                "confidence": 0.95,
                "metric": col_mention,
                "subject": "tổng",
            }

        # I. AVERAGE
        if any(w in prompt_norm for w in ["trung binh", "binh quan", "avg", "average", "mean"]):
            col_mention = cls._extract_candidate_metric(prompt_norm, ["trung binh", "binh quan", "avg", "average", "mean"])
            return {
                "intent": "AVERAGE",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "column_mention": col_mention,
                "target_type": target_type,
                "confidence": 0.95,
                "metric": col_mention,
                "subject": "trung bình",
            }

        # J. COUNT / COUNT_DISTINCT
        if any(w in prompt_norm for w in ["bao nhieu", "so luong", "dem", "count"]):
            if any(w in prompt_norm for w in ["khac nhau", "duy nhat", "unique", "distinct"]):
                col_mention = cls._extract_candidate_metric(prompt_norm, ["khac nhau", "duy nhat", "unique", "distinct", "dem", "bao nhieu"])
                return {
                    "intent": "COUNT_DISTINCT",
                    "sheet": resolved_sheet,
                    "sheet_mention": sheet_mention,
                    "column_mention": col_mention,
                    "target_type": target_type,
                    "confidence": 0.9,
                    "metric": col_mention,
                    "subject": "số lượng duy nhất",
                }
            return {
                "intent": "COUNT",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "column_mention": None,
                "target_type": target_type,
                "confidence": 0.9,
                "metric": None,
                "subject": "số lượng dòng",
            }

        # K. GROUP_BY / COMPARE GROUPS
        if any(w in prompt_norm for w in ["so sanh", "doi chieu", "theo phong ban", "theo nhom", "group by"]):
            return {
                "intent": "GROUP_BY",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "target_type": target_type,
                "confidence": 0.85,
                "metric": None,
                "subject": "so sánh nhóm",
            }

        # L. GENERATE_FORMULA
        if any(w in prompt_norm for w in ["viet cong thuc", "cong thuc", "ham excel", "ham tinh", "formula", "tao cong thuc"]):
            return {
                "intent": "GENERATE_FORMULA",
                "sheet": resolved_sheet,
                "sheet_mention": sheet_mention,
                "column_mention": None,
                "target_type": target_type,
                "confidence": 0.95,
                "metric": None,
                "subject": "công thức Excel",
            }

        # M. SUMMARY / OVERVIEW
        return {
            "intent": "SUMMARY",
            "sheet": resolved_sheet,
            "sheet_mention": sheet_mention,
            "column_mention": None,
            "target_type": target_type,
            "confidence": 0.7,
            "metric": None,
            "subject": "tổng quan bảng tính",
        }

    @classmethod
    def _extract_candidate_metric(cls, norm_text: str, trigger_words: List[str]) -> Optional[str]:
        cleaned = norm_text
        for tw in trigger_words:
            cleaned = cleaned.replace(tw, " ")
        # Remove common question filler tokens
        for filler in ["ai co", "nguoi co", "nhan vien co", "tim", "kiem tra", "tinh", "xem", "cho biet", "la bao nhieu", "cua", "trong", "o", "tai"]:
            cleaned = re.sub(rf"\b{re.escape(filler)}\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned if len(cleaned) >= 2 else None


analysis_intent_parser = AnalysisIntentParser()
