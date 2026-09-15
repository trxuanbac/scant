import datetime
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.ai.gateway import ai_gateway
from app.services.ai.types import AIRequest, AITaskType
from app.services.data.analysis_contracts import AnalysisScope
from app.services.data.data_quality_service import scan_quality


class SheetAnalysisService:
    """
    Interactive AI Excel Data Analysis Engine.
    Provides deterministic mathematical & statistical profiling across 100% of rows,
    data quality scanning, automatic chart recommendations, and grounded AI insights.
    """

    _cache: Dict[str, Dict[str, Any]] = {}
    CACHE_VERSION = "v2"

    @classmethod
    def _compute_cache_key(cls, file_path: str, sheet_name: str) -> str:
        try:
            stat = Path(file_path).stat()
            raw = f"{file_path}_{stat.st_mtime}_{stat.st_size}_{sheet_name}_{cls.CACHE_VERSION}"
        except Exception:
            raw = f"{file_path}_{sheet_name}_{cls.CACHE_VERSION}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def detect_header_row(cls, df: pd.DataFrame, max_check: int = 6) -> int:
        """
        Detects actual column header row in case of merged title banners or blank top rows.
        """
        best_row = 0
        best_score = -1
        for r_idx in range(min(len(df), max_check)):
            row_vals = df.iloc[r_idx].dropna().tolist()
            if not row_vals:
                continue
            text_count = sum(1 for v in row_vals if isinstance(v, str) and len(v.strip()) > 0)
            unique_count = len(set(str(v).strip() for v in row_vals if v is not None and str(v).strip()))
            total_non_null = len(row_vals)
            # Favor rows with multiple distinct text strings
            score = text_count * 3 + unique_count * 2 + total_non_null
            if score > best_score and unique_count >= 2:
                best_score = score
                best_row = r_idx
        return best_row

    @classmethod
    def load_sheet_dataframe(cls, file_path: str, sheet_name: Optional[str] = None) -> Tuple[pd.DataFrame, str, List[str]]:
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext in [".xlsx", ".xls", ".xlsm"]:
            excel = pd.ExcelFile(file_path)
            all_sheets = excel.sheet_names
            target_sheet = sheet_name if (sheet_name and sheet_name in all_sheets) else (all_sheets[0] if all_sheets else "Sheet1")
            
            # Read raw without header first to detect header row
            raw_df = pd.read_excel(file_path, sheet_name=target_sheet, header=None)
            if raw_df.empty:
                return pd.DataFrame(), target_sheet, all_sheets

            hdr_idx = cls.detect_header_row(raw_df)
            header_vals = raw_df.iloc[hdr_idx].tolist()
            header = []
            seen_cols = {}
            for i, v in enumerate(header_vals):
                col_str = str(v).strip() if (v is not None and not pd.isna(v) and str(v).strip()) else f"Cột_{i + 1}"
                # Handle duplicate column names
                if col_str in seen_cols:
                    seen_cols[col_str] += 1
                    col_str = f"{col_str}_{seen_cols[col_str]}"
                else:
                    seen_cols[col_str] = 1
                header.append(col_str)

            body_df = raw_df.iloc[hdr_idx + 1:].copy().reset_index(drop=True)
            body_df.columns = header
            # Drop entirely empty rows
            clean_df = body_df.dropna(how="all").reset_index(drop=True)
            return clean_df, target_sheet, all_sheets

        # CSV fallback
        try:
            raw_df = pd.read_csv(file_path, header=None)
        except UnicodeDecodeError:
            raw_df = pd.read_csv(file_path, header=None, encoding="latin-1")

        if raw_df.empty:
            return pd.DataFrame(), "CSV", ["CSV"]

        hdr_idx = cls.detect_header_row(raw_df)
        header_vals = raw_df.iloc[hdr_idx].tolist()
        header = [str(v).strip() if (v is not None and not pd.isna(v) and str(v).strip()) else f"Cột_{i + 1}" for i, v in enumerate(header_vals)]
        body_df = raw_df.iloc[hdr_idx + 1:].copy().reset_index(drop=True)
        body_df.columns = header
        clean_df = body_df.dropna(how="all").reset_index(drop=True)
        return clean_df, "CSV", ["CSV"]

    @classmethod
    def infer_column_type(cls, series: pd.Series, col_name: str) -> str:
        name_lower = col_name.lower().strip()
        non_null = series.dropna()
        if non_null.empty:
            return "unknown"

        sample_strs = [str(v).strip() for v in non_null.head(50) if str(v).strip()]

        # 1. Check ID / Code / Identity / Phone keywords
        if any(k in name_lower for k in [
            "mã", "ma", "code", "id", "stt", "số thứ tự", "sku", "uuid",
            "cccd", "cmnd", "bks", "biển kiểm soát", "bien kiem soat", "biển số", "bien so",
            "điện thoại", "dien thoai", "sđt", "sdt", "phone", "mst", "hợp đồng", "hop dong"
        ]):
            return "id_code"

        # 2. Check Weight / Payload / Capacity (e.g. Tải Trọng with values 1T9, 5T, 8T, 15T, 2.5 tấn) -> category or numeric, NEVER date
        if any(k in name_lower for k in ["tải trọng", "tai trong", "trọng lượng", "trong luong", "khối lượng", "payload", "capacity", "tonnage"]):
            numeric_conv = pd.to_numeric(non_null, errors="coerce")
            if numeric_conv.notna().mean() > 0.8:
                return "numeric"
            return "category"

        # 3. Check Transport / Flight Schedule Time keywords (STD, STA, ATD, ATA, ETD, ETA, Giờ...) -> Date/Time, NEVER currency
        if any(name_lower == k or f" {k}" in name_lower or f"{k} " in name_lower for k in ["std", "sta", "atd", "ata", "etd", "eta", "giờ", "gio", "time"]):
            return "date"

        # 4. Check currency / price keywords in name
        if any(k in name_lower for k in ["giá", "gia", "đơn giá", "don gia", "tiền", "tien", "vnd", "usd", "lương", "luong", "thành tiền", "thanh tien", "cost", "revenue", "price", "cước", "cuoc", "phí", "phi"]):
            return "currency"

        # 5. Check percentage keywords
        if any(k in name_lower for k in ["tỷ lệ", "ty le", "phần trăm", "phan tram", "%", "pct", "rate", "ratio"]):
            return "percentage"

        # 6. Check boolean
        if set(non_null.astype(str).str.lower().unique()).issubset({"true", "false", "1", "0", "có", "không", "co", "khong", "yes", "no"}):
            return "boolean"

        # 7. Check numeric conversion
        numeric_conv = pd.to_numeric(non_null, errors="coerce")
        if numeric_conv.notna().mean() > 0.8:
            return "numeric"

        # 8. Check date conversion (only if not looks like a code or weight string like 1T9)
        has_tonnage_pattern = any(re.match(r"^\d+[Tt]\d*$", s) for s in sample_strs)
        if not has_tonnage_pattern:
            try:
                # Require explicit date format or standard date delimiters
                has_date_delimiters = any("/" in s or "-" in s or ":" in s for s in sample_strs[:10])
                if has_date_delimiters:
                    date_conv = pd.to_datetime(non_null, errors="coerce", format="mixed")
                    if date_conv.notna().mean() > 0.8:
                        return "date"
            except Exception:
                pass

        # 9. Check category vs text
        unique_ratio = non_null.nunique() / max(len(non_null), 1)
        if unique_ratio < 0.3 or non_null.nunique() <= 20:
            return "category"

        return "text"

    @classmethod
    def compute_deterministic_statistics(cls, df: pd.DataFrame, sheet_name: str) -> Dict[str, Any]:
        total_rows = len(df)
        total_cols = len(df.columns)
        total_cells = total_rows * total_cols
        empty_cells = int(df.isnull().sum().sum())
        populated_cells = total_cells - empty_cells
        empty_pct = round((empty_cells / total_cells * 100), 2) if total_cells > 0 else 0.0

        duplicate_rows = int(df.duplicated().sum())
        duplicate_pct = round((duplicate_rows / total_rows * 100), 2) if total_rows > 0 else 0.0

        columns_meta: List[Dict[str, Any]] = []
        type_counts = {
            "numeric": 0, "currency": 0, "percentage": 0,
            "date": 0, "category": 0, "text": 0,
            "boolean": 0, "id_code": 0, "unknown": 0
        }

        numeric_cols_for_charts: List[str] = []
        category_cols_for_charts: List[str] = []
        date_cols_for_charts: List[str] = []

        for col_name in df.columns:
            series = df[col_name]
            col_type = cls.infer_column_type(series, col_name)
            type_counts[col_type] = type_counts.get(col_type, 0) + 1

            non_null_count = int(series.notna().sum())
            missing_count = int(series.isna().sum())
            missing_pct = round((missing_count / total_rows * 100), 2) if total_rows > 0 else 0.0
            unique_count = int(series.nunique(dropna=True))
            unique_pct = round((unique_count / max(non_null_count, 1) * 100), 2)

            sample_vals = [str(v) for v in series.dropna().head(5).tolist()]

            col_info: Dict[str, Any] = {
                "name": str(col_name),
                "type": col_type,
                "total_count": total_rows,
                "non_null_count": non_null_count,
                "missing_count": missing_count,
                "missing_pct": missing_pct,
                "unique_count": unique_count,
                "unique_pct": unique_pct,
                "sample_values": sample_vals,
            }

            # Numeric & Currency stats
            if col_type in ["numeric", "currency", "percentage"] or pd.to_numeric(series, errors="coerce").notna().mean() > 0.7:
                num_s = pd.to_numeric(series, errors="coerce").dropna()
                if not num_s.empty:
                    q1 = float(num_s.quantile(0.25))
                    q3 = float(num_s.quantile(0.75))
                    iqr = q3 - q1
                    outliers_count = int(((num_s < (q1 - 1.5 * iqr)) | (num_s > (q3 + 1.5 * iqr))).sum())

                    col_info.update({
                        "min": round(float(num_s.min()), 2),
                        "max": round(float(num_s.max()), 2),
                        "mean": round(float(num_s.mean()), 2),
                        "median": round(float(num_s.median()), 2),
                        "sum": round(float(num_s.sum()), 2),
                        "std": round(float(num_s.std()), 2) if len(num_s) > 1 else 0.0,
                        "q1": round(q1, 2),
                        "q3": round(q3, 2),
                        "outliers_count": outliers_count,
                    })
                    if col_type in ["numeric", "currency"] and col_name not in numeric_cols_for_charts:
                        numeric_cols_for_charts.append(col_name)

            # Categorical stats
            if col_type in ["category", "text", "boolean", "id_code"]:
                val_counts = series.dropna().value_counts().head(8)
                top_values = [
                    {
                        "value": str(k),
                        "count": int(v),
                        "pct": round(int(v) / max(non_null_count, 1) * 100, 1),
                    }
                    for k, v in val_counts.items()
                ]
                col_info["top_values"] = top_values
                if col_type in ["category", "text"] and unique_count > 1 and unique_count <= 25:
                    if col_name not in category_cols_for_charts:
                        category_cols_for_charts.append(col_name)

            # Date stats
            if col_type == "date":
                try:
                    dt_s = pd.to_datetime(series, errors="coerce").dropna()
                    if not dt_s.empty:
                        min_d = dt_s.min().strftime("%Y-%m-%d")
                        max_d = dt_s.max().strftime("%Y-%m-%d")
                        col_info["min_date"] = min_d
                        col_info["max_date"] = max_d
                        col_info["duration_days"] = int((dt_s.max() - dt_s.min()).days)
                        if col_name not in date_cols_for_charts:
                            date_cols_for_charts.append(col_name)
                except Exception:
                    pass

            columns_meta.append(col_info)

        # Overview summary
        overview = {
            "sheet_name": sheet_name,
            "total_rows": total_rows,
            "total_columns": total_cols,
            "total_cells": total_cells,
            "populated_cells": populated_cells,
            "empty_cells": empty_cells,
            "empty_pct": empty_pct,
            "duplicate_rows": duplicate_rows,
            "duplicate_pct": duplicate_pct,
            "numeric_columns_count": type_counts["numeric"] + type_counts["currency"] + type_counts["percentage"],
            "text_columns_count": type_counts["text"],
            "category_columns_count": type_counts["category"],
            "date_columns_count": type_counts["date"],
            "id_columns_count": type_counts["id_code"],
        }

        return {
            "overview": overview,
            "columns": columns_meta,
            "numeric_cols_for_charts": numeric_cols_for_charts,
            "category_cols_for_charts": category_cols_for_charts,
            "date_cols_for_charts": date_cols_for_charts,
        }

    @classmethod
    def scan_data_quality(cls, df: pd.DataFrame, columns_meta: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        issue_id = 1
        total_rows = max(len(df), 1)

        # 1. Check Missing Values
        for col in columns_meta:
            missing_count = col["missing_count"]
            missing_pct = col["missing_pct"]
            if missing_count > 0:
                severity = "high" if missing_pct > 25 else ("medium" if missing_pct > 8 else "low")
                issues.append({
                    "id": f"DQ_{issue_id:03d}",
                    "type": "missing_values",
                    "severity": severity,
                    "title": f"Thiếu dữ liệu tại cột {col['name']}",
                    "message": f"Có {missing_count} ô ({missing_pct}%) bị trống trong cột '{col['name']}'.",
                    "affected_rows_count": missing_count,
                    "affected_columns": [col["name"]],
                    "suggestion": "Kiểm tra bổ sung dữ liệu bị khuyết hoặc xem xét gán giá trị mặc định.",
                })
                issue_id += 1

        # 2. Check Duplicate Rows
        dup_count = int(df.duplicated().sum())
        if dup_count > 0:
            dup_pct = round(dup_count / total_rows * 100, 1)
            severity = "high" if dup_pct > 10 else "medium"
            issues.append({
                "id": f"DQ_{issue_id:03d}",
                "type": "duplicate_rows",
                "severity": severity,
                "title": "Phát hiện dòng dữ liệu trùng lặp",
                "message": f"Có {dup_count} dòng ({dup_pct}%) có nội dung trùng lặp hoàn toàn với dòng khác.",
                "affected_rows_count": dup_count,
                "affected_columns": list(df.columns[:5]),
                "suggestion": "Loại bỏ các dòng trùng lặp để tránh tính toán đúp chỉ số KPI.",
            })
            issue_id += 1

        # 3. Check Outliers in Numeric Columns
        for col in columns_meta:
            outliers = col.get("outliers_count", 0)
            if outliers > 0:
                issues.append({
                    "id": f"DQ_{issue_id:03d}",
                    "type": "outliers",
                    "severity": "low",
                    "title": f"Giá trị ngoại lai tại cột {col['name']}",
                    "message": f"Có {outliers} giá trị bất thường (ngoài ngưỡng IQR) tại cột '{col['name']}' (Min: {col.get('min'):,}, Max: {col.get('max'):,}).",
                    "affected_rows_count": outliers,
                    "affected_columns": [col["name"]],
                    "suggestion": "Xác nhận lại tính chính xác của các giá trị cực trị trước khi ra quyết định kinh doanh.",
                })
                issue_id += 1

        # 4. Check Inconsistent Whitespace / Text Spacing
        for col in columns_meta:
            if col["type"] in ["text", "category"]:
                series = df[col["name"]].dropna().astype(str)
                has_whitespace = series.apply(lambda s: len(s) != len(s.strip()) or "  " in s).sum()
                if has_whitespace > 0:
                    issues.append({
                        "id": f"DQ_{issue_id:03d}",
                        "type": "whitespace",
                        "severity": "low",
                        "title": f"Khoảng trắng thừa tại cột {col['name']}",
                        "message": f"Có {has_whitespace} ô chứa khoảng trắng thừa ở đầu/cuối hoặc giữa các từ.",
                        "affected_rows_count": int(has_whitespace),
                        "affected_columns": [col["name"]],
                        "suggestion": "Chuẩn hóa loại bỏ khoảng trắng thừa để việc gom nhóm danh mục đạt độ chính xác cao.",
                    })
                    issue_id += 1

        return issues

    @classmethod
    def generate_chart_recommendations(
        cls,
        df: pd.DataFrame,
        stat_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        charts: List[Dict[str, Any]] = []
        chart_id = 1
        num_cols = stat_result.get("numeric_cols_for_charts", [])
        cat_cols = stat_result.get("category_cols_for_charts", [])
        date_cols = stat_result.get("date_cols_for_charts", [])

        # 1. Bar Chart: Category vs Primary Numeric Sum/Average
        if cat_cols and num_cols:
            cat_col = cat_cols[0]
            num_col = num_cols[0]
            try:
                temp_df = df[[cat_col, num_col]].copy()
                temp_df[num_col] = pd.to_numeric(temp_df[num_col], errors="coerce").fillna(0)
                grouped = temp_df.groupby(cat_col)[num_col].agg(["sum", "mean", "count"]).reset_index()
                # Sort by sum descending, limit top 10
                grouped = grouped.sort_values(by="sum", ascending=False).head(10)
                data_points = [
                    {
                        "label": str(row[cat_col]),
                        "value": round(float(row["sum"]), 2),
                        "mean": round(float(row["mean"]), 2),
                        "count": int(row["count"]),
                    }
                    for _, row in grouped.iterrows()
                ]
                charts.append({
                    "id": f"CHART_{chart_id:02d}",
                    "title": f"Tổng {num_col} theo {cat_col}",
                    "type": "bar",
                    "x_axis": cat_col,
                    "y_axis": num_col,
                    "data": data_points,
                    "description": f"So sánh phân bổ tổng {num_col} giữa các {cat_col}.",
                })
                chart_id += 1
            except Exception:
                pass

        # 2. Donut / Pie Chart: Category Frequency Composition
        if cat_cols:
            cat_col = cat_cols[0] if len(cat_cols) == 1 else cat_cols[min(1, len(cat_cols) - 1)]
            try:
                counts = df[cat_col].value_counts().head(7)
                total = counts.sum()
                data_points = [
                    {
                        "label": str(k),
                        "value": int(v),
                        "pct": round(int(v) / max(total, 1) * 100, 1),
                    }
                    for k, v in counts.items()
                ]
                charts.append({
                    "id": f"CHART_{chart_id:02d}",
                    "title": f"Cơ cấu phân bổ theo {cat_col}",
                    "type": "pie",
                    "data": data_points,
                    "description": f"Tỷ trọng các nhóm trong cột {cat_col}.",
                })
                chart_id += 1
            except Exception:
                pass

        # 3. Horizontal Bar or Second Numeric Breakdown
        if len(num_cols) >= 2 and cat_cols:
            cat_col = cat_cols[0]
            num_col2 = num_cols[1]
            try:
                temp_df2 = df[[cat_col, num_col2]].copy()
                temp_df2[num_col2] = pd.to_numeric(temp_df2[num_col2], errors="coerce").fillna(0)
                grouped2 = temp_df2.groupby(cat_col)[num_col2].sum().reset_index().sort_values(by=num_col2, ascending=False).head(10)
                data_points = [
                    {"label": str(row[cat_col]), "value": round(float(row[num_col2]), 2)}
                    for _, row in grouped2.iterrows()
                ]
                charts.append({
                    "id": f"CHART_{chart_id:02d}",
                    "title": f"{num_col2} theo {cat_col}",
                    "type": "horizontal_bar",
                    "x_axis": cat_col,
                    "y_axis": num_col2,
                    "data": data_points,
                    "description": f"Phân tích thứ hạng {num_col2} theo từng {cat_col}.",
                })
                chart_id += 1
            except Exception:
                pass

        # 4. Line Chart: Date vs Numeric (if date exists)
        if date_cols and num_cols:
            date_col = date_cols[0]
            num_col = num_cols[0]
            try:
                temp_df = df.copy()
                temp_df["_dt"] = pd.to_datetime(temp_df[date_col], errors="coerce")
                temp_df[num_col] = pd.to_numeric(temp_df[num_col], errors="coerce").fillna(0)
                temp_df = temp_df.dropna(subset=["_dt"])
                if not temp_df.empty:
                    grouped_date = temp_df.groupby(temp_df["_dt"].dt.strftime("%Y-%m-%d"))[num_col].sum().reset_index()
                    data_points = [
                        {"label": str(row["_dt"]), "value": round(float(row[num_col]), 2)}
                        for _, row in grouped_date.head(20).iterrows()
                    ]
                    charts.append({
                        "id": f"CHART_{chart_id:02d}",
                        "title": f"Xu hướng {num_col} theo thời gian ({date_col})",
                        "type": "line",
                        "x_axis": date_col,
                        "y_axis": num_col,
                        "data": data_points,
                        "description": f"Biến động {num_col} qua các mốc thời gian.",
                    })
            except Exception:
                pass

        return charts

    @classmethod
    async def generate_grounded_ai_insights(
        cls,
        sheet_name: str,
        overview: Dict[str, Any],
        columns: List[Dict[str, Any]],
        quality_issues: List[Dict[str, Any]],
        sample_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Generates grounded, strictly verified AI insights using structured JSON output.
        """
        # Prepare compact verified context
        stats_summary = {
            "sheet": sheet_name,
            "total_rows": overview["total_rows"],
            "total_cols": overview["total_columns"],
            "columns": [
                {
                    "name": col["name"],
                    "type": col["type"],
                    "nulls": col["missing_count"],
                    "unique": col["unique_count"],
                    "min": col.get("min"),
                    "max": col.get("max"),
                    "mean": col.get("mean"),
                    "sum": col.get("sum"),
                    "top_values": col.get("top_values", [])[:4],
                }
                for col in columns[:15]
            ],
            "quality_warnings": [q["message"] for q in quality_issues[:6]],
            "sample_data": sample_rows[:5],
        }

        prompt = f"""Bạn là Chuyên gia Cao cấp về Phân tích Dữ liệu Bảng tính (Senior Excel Data Analyst).
Dưới đây là TOÀN BỘ số liệu đã được tính toán CHÍNH XÁC 100% bằng Pandas Engine từ sheet "{sheet_name}":

```json
{json.dumps(stats_summary, ensure_ascii=False, indent=2)}
```

NHIỆM VỤ:
Phân tích sheet dữ liệu này và trả về ĐÚNG MỘT JSON object hợp lệ (không kèm text markdown bên ngoài) theo cấu trúc:
{{
  "summary": "1-3 đoạn văn phân tích tổng quan nội dung, quy mô và đặc trưng dữ liệu của sheet.",
  "key_findings": [
    {{
      "title": "Tên phát hiện ngắn gọn",
      "description": "Mô tả chi tiết phân tích",
      "evidence": "Bằng chứng số liệu thực tế cụ thể từ dữ liệu",
      "importance": "high" // hoặc "medium", "low"
    }}
  ],
  "trends": [
    "Mô tả quy luật hoặc xu hướng phân bố 1",
    "Mô tả quy luật hoặc xu hướng phân bố 2"
  ],
  "anomalies": [
    "Điểm bất thường hoặc ngoại lai đáng chú ý (nếu có)"
  ],
  "recommendations": [
    "Đề xuất hành động kinh doanh hoặc cải thiện chất lượng dữ liệu 1",
    "Đề xuất hành động 2"
  ],
  "business_meaning": "Ý nghĩa nghiệp vụ thực tế của bảng tính này."
}}

QUY TẮC BẮT BUỘC:
1. TUYỆT ĐỐI KHÔNG BỊA SỐ LIỆU. Mọi số liệu trong nhận xét phải trích xuất chính xác từ JSON trên.
2. Nếu không đủ dữ liệu để kết luận vấn đề nào, hãy ghi rõ "Dữ liệu nguồn chưa đủ thông tin để kết luận".
3. Viết bằng tiếng Việt chuyên nghiệp, súc tích, chuẩn văn phong phân tích kinh doanh.
"""

        try:
            req = AIRequest(
                task_type=AITaskType.DATA_NARRATIVE,
                prompt=prompt,
                max_tokens=2048,
                temperature=0.2,
            )
            resp = await ai_gateway.execute(req)
            raw_text = resp.text.strip()
            
            # Extract JSON block if wrapped in markdown code fence
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
            if json_match:
                clean_json_str = json_match.group(1).strip()
            else:
                clean_json_str = raw_text

            parsed_ai = json.loads(clean_json_str)
            return parsed_ai
        except Exception as e:
            # Fallback deterministic narrative if AI fails
            return {
                "summary": f"Sheet '{sheet_name}' chứa {overview['total_rows']} dòng dữ liệu và {overview['total_columns']} cột. Dữ liệu bao gồm {overview['numeric_columns_count']} trường số liệu và {overview['category_columns_count']} trường danh mục phân loại.",
                "key_findings": [
                    {
                        "title": f"Quy mô dữ liệu sheet {sheet_name}",
                        "description": f"Tổng cộng {overview['total_rows']:,} dòng và {overview['total_columns']} cột với tỷ lệ ô trống là {overview['empty_pct']}%.",
                        "evidence": f"{overview['populated_cells']:,}/{overview['total_cells']:,} ô có dữ liệu.",
                        "importance": "high" if overview["empty_pct"] < 10 else "medium",
                    }
                ],
                "trends": [
                    f"Có {overview['duplicate_rows']} dòng trùng lặp ({overview['duplicate_pct']}%) trong sheet."
                ],
                "anomalies": [q["message"] for q in quality_issues[:3]],
                "recommendations": [
                    "Sử dụng số liệu đã kiểm chứng để lập báo cáo và đối chiếu định kỳ."
                ],
                "business_meaning": f"Bảng dữ liệu {sheet_name}.",
            }

    @classmethod
    async def analyze_sheet(
        cls,
        file_path: str,
        sheet_name: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Main entry point for sheet-level interactive analysis.
        Uses in-memory caching to avoid re-computing or re-calling AI when switching sheets.
        """
        clean_file_path = str(file_path).strip()
        cache_key = cls._compute_cache_key(clean_file_path, sheet_name or "default")

        if not force_refresh and cache_key in cls._cache:
            return cls._cache[cache_key]

        # 1. Load DataFrame for specific sheet
        df, resolved_sheet_name, all_sheets = cls.load_sheet_dataframe(clean_file_path, sheet_name=sheet_name)
        if df.empty:
            empty_result = {
                "sheet_name": resolved_sheet_name,
                "all_sheets": all_sheets,
                "overview": {
                    "sheet_name": resolved_sheet_name,
                    "total_rows": 0, "total_columns": 0, "total_cells": 0,
                    "populated_cells": 0, "empty_cells": 0, "empty_pct": 0,
                    "duplicate_rows": 0, "duplicate_pct": 0,
                    "numeric_columns_count": 0, "text_columns_count": 0,
                    "category_columns_count": 0, "date_columns_count": 0, "id_columns_count": 0,
                },
                "columns": [],
                "data_quality_issues": [],
                "charts": [],
                "ai_insights": {
                    "summary": f"Sheet '{resolved_sheet_name}' không có dòng dữ liệu nào.",
                    "key_findings": [],
                    "trends": [],
                    "anomalies": [],
                    "recommendations": [],
                    "business_meaning": "Sheet trống.",
                },
                "sample_rows": [],
            }
            cls._cache[cache_key] = empty_result
            return empty_result

        # 2. Deterministic Statistics across ALL rows
        stat_result = cls.compute_deterministic_statistics(df, resolved_sheet_name)
        overview = stat_result["overview"]
        columns_meta = stat_result["columns"]

        # 3. Data Quality Scan
        quality_issues = scan_quality(
            clean_file_path,
            AnalysisScope("sheet", (resolved_sheet_name,)),
        )["issues"]

        # 4. Chart Auto-Recommendations
        charts = cls.generate_chart_recommendations(df, stat_result)

        # 5. Extract clean sample rows (first 25 rows)
        sample_records = df.head(25).replace({np.nan: None}).to_dict(orient="records")
        clean_samples = [
            {str(k): (round(float(v), 2) if isinstance(v, (np.floating, float)) and not math.isnan(v) else (int(v) if isinstance(v, (np.integer, int)) else str(v) if v is not None else "")) for k, v in row.items()}
            for row in sample_records
        ]

        # 6. Grounded AI Insights
        ai_insights = await cls.generate_grounded_ai_insights(
            sheet_name=resolved_sheet_name,
            overview=overview,
            columns=columns_meta,
            quality_issues=quality_issues,
            sample_rows=clean_samples,
        )

        final_result = {
            "sheet_name": resolved_sheet_name,
            "all_sheets": all_sheets,
            "overview": overview,
            "columns": columns_meta,
            "data_quality_issues": quality_issues,
            "charts": charts,
            "ai_insights": ai_insights,
            "sample_rows": clean_samples,
        }

        # Cache result
        cls._cache[cache_key] = final_result
        return final_result


sheet_analysis_service = SheetAnalysisService()
