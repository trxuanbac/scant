import json
import re
import unicodedata
import httpx
from typing import Any, AsyncGenerator, Dict, List, Optional
from app.core.config import settings
from app.services.ai.base import AIProvider


class GeminiProvider(AIProvider):
    """Google Gemini AI Provider implementation."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.default_model = settings.DEFAULT_AI_MODEL or "gemini-2.5-flash"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_model = model or self.default_model

        if not self.api_key:
            if not settings.allow_ai_offline_fallback:
                raise RuntimeError("GEMINI_API_KEY is required when AI offline fallback is disabled.")
            # High-fidelity fallback generator for local offline mode / tests
            return self._mock_academic_fallback(prompt, response_format)

        url = f"{self.base_url}/{target_model}:generateContent?key={self.api_key}"
        
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Context: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow the academic guidelines."}]})
        
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }

        if response_format == "json":
            payload["generationConfig"]["responseMimeType"] = "application/json"

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                candidates = data.get("candidates", [])
                if not candidates:
                    return {"text": "", "tokens_used": 0, "provider": "gemini", "model": target_model}

                candidate = candidates[0]
                content_parts = candidate.get("content", {}).get("parts", [])
                text = "".join([p.get("text", "") for p in content_parts])
                usage = data.get("usageMetadata", {})
                tokens_used = usage.get("totalTokenCount", len(text) // 4)

                return {
                    "text": text,
                    "tokens_used": tokens_used,
                    "usage": {"prompt_tokens": usage.get("promptTokenCount"), "completion_tokens": (usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0))},
                    "provider": "gemini",
                    "model": target_model,
                }
            except Exception as e:
                if not settings.allow_ai_offline_fallback:
                    raise
                # Fallback to local deterministic generator if network fails
                return self._mock_academic_fallback(prompt, response_format)

    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        res = await self.generate(prompt, system_prompt, model, temperature, max_tokens)
        full_text = res.get("text", "")
        # Yield in realistic stream chunks (e.g. 5-10 words per chunk)
        words = full_text.split(" ")
        chunk_size = 6
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size]) + " "
            yield chunk

    @staticmethod
    def _prompt_value(prompt: str, labels: List[str]) -> str:
        for line in (prompt or "").splitlines():
            stripped = line.strip()
            for label in labels:
                if stripped.upper().startswith(label.upper()):
                    return stripped.split(":", 1)[1].strip().strip('"')
        return ""

    @staticmethod
    def _normalize_for_match(value: str) -> str:
        normalized = unicodedata.normalize("NFD", value or "")
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", normalized.lower().replace("đ", "d")).strip()

    @classmethod
    def _prompt_block(cls, prompt: str, labels: List[str], end_labels: List[str]) -> str:
        value = prompt or ""
        for label in labels:
            match = re.search(
                rf"(?im)^[ \t]*{re.escape(label)}[ \t]*:[ \t]*(?:\r?\n)?",
                value,
            )
            if not match:
                continue
            remainder = value[match.end():]
            end_positions = []
            for end_label in end_labels:
                end_match = re.search(
                    rf"(?im)^[ \t]*{re.escape(end_label)}[ \t]*:",
                    remainder,
                )
                if end_match:
                    end_positions.append(end_match.start())
            if end_positions:
                remainder = remainder[:min(end_positions)]
            else:
                paragraph_end = re.search(r"\r?\n[ \t]*\r?\n", remainder)
                if paragraph_end:
                    remainder = remainder[:paragraph_end.start()]
            stripped_remainder = remainder.strip()
            if stripped_remainder.startswith(('"', '“')):
                opening = stripped_remainder[0]
                closing = '”' if opening == '“' else '"'
                closing_index = stripped_remainder.rfind(closing)
                if closing_index > 0:
                    stripped_remainder = stripped_remainder[1:closing_index]
            remainder = stripped_remainder
            return re.sub(r"\s+", " ", remainder).strip().strip('"“”').strip()
        return ""

    @classmethod
    def _document_type(cls, value: str) -> str:
        normalized = cls._normalize_for_match(value)
        if normalized in {"", "tu dong", "tu dong phan loai", "auto", "automatic"}:
            return ""
        aliases = {
            "business report": "business_report",
            "data analysis": "data_analysis",
            "market research": "market_research",
            "financial report": "financial",
            "technical documentation": "technical",
        }
        return aliases.get(normalized, normalized.replace(" ", "_"))

    @classmethod
    def _is_market_topic(cls, value: str) -> bool:
        normalized = cls._normalize_for_match(value)
        if any(term in normalized for term in (
            "thi truong", "market research", "market analysis", "market size", "go to market",
        )):
            return True
        signals = (
            ("khach hang", "customer demand", "consumer demand"),
            ("doi thu", "competitor", "competitive landscape"),
            ("phan khuc", "segmentation", "market segment"),
            ("tham nhap", "market entry"),
        )
        return sum(any(term in normalized for term in group) for group in signals) >= 2

    @classmethod
    def _use_market_intent_fallback(cls, prompt: str) -> bool:
        selected_type = cls._document_type(cls._prompt_value(
            prompt,
            ["DANH MỤC BAN ĐẦU (NẾU CÓ)", "DANH MUC BAN DAU (NEU CO)"],
        ))
        if selected_type:
            return selected_type == "market_research"
        idea = cls._prompt_block(
            prompt,
            ["Ý TƯỞNG CỦA NGƯỜI DÙNG", "Y TUONG CUA NGUOI DUNG"],
            ["DANH MỤC BAN ĐẦU (NẾU CÓ)", "DANH MUC BAN DAU (NEU CO)"],
        )
        return cls._is_market_topic(idea)

    @classmethod
    def _use_market_outline_fallback(cls, prompt: str) -> bool:
        document_type = cls._document_type(cls._prompt_value(
            prompt,
            ["LOẠI TÀI LIỆU", "LOAI TAI LIEU"],
        ))
        if document_type:
            return document_type == "market_research"
        return cls._is_market_topic(prompt)

    @classmethod
    def _mock_market_intent(cls, prompt: str) -> Dict[str, Any]:
        title = cls._prompt_block(
            prompt,
            ["Ý TƯỞNG CỦA NGƯỜI DÙNG", "Y TUONG CUA NGUOI DUNG"],
            ["DANH MỤC BAN ĐẦU (NẾU CÓ)", "DANH MUC BAN DAU (NEU CO)"],
        )
        title = title or "Nghiên cứu thị trường"
        return {
            "suggested_title": title,
            "suggested_type": "market_research",
            "objective": f"Đánh giá thị trường, khách hàng, cạnh tranh và cơ hội chiến lược cho đề tài {title}.",
            "target_audience": "Ban lãnh đạo, bộ phận chiến lược và phát triển kinh doanh",
            "key_themes": ["Quy mô và xu hướng thị trường", "Khách hàng và phân khúc", "Cạnh tranh", "Chiến lược thâm nhập"],
            "suggested_custom_fields": [],
            "data_requirements": "Số liệu thị trường, chính sách, hành vi khách hàng và thông tin đối thủ từ nguồn có thể kiểm chứng.",
            "research_requirements": "Ưu tiên nguồn chính phủ, tổ chức ngành, báo cáo doanh nghiệp và nghiên cứu có ngày công bố rõ ràng.",
        }

    @classmethod
    def _mock_general_intent(cls, prompt: str) -> Dict[str, Any]:
        title = cls._prompt_block(
            prompt,
            ["Ý TƯỞNG CỦA NGƯỜI DÙNG", "Y TUONG CUA NGUOI DUNG"],
            ["DANH MỤC BAN ĐẦU (NẾU CÓ)", "DANH MUC BAN DAU (NEU CO)"],
        ) or "Báo cáo chuyên môn"
        selected_type = cls._document_type(cls._prompt_value(
            prompt,
            ["DANH MỤC BAN ĐẦU (NẾU CÓ)", "DANH MUC BAN DAU (NEU CO)"],
        ))
        suggested_type = selected_type or "business_report"
        return {
            "suggested_title": title,
            "suggested_type": suggested_type,
            "objective": f"Phân tích yêu cầu và xây dựng tài liệu phù hợp cho đề tài {title}.",
            "target_audience": "Ban lãnh đạo, nhóm chuyên môn và các bên liên quan",
            "key_themes": ["Bối cảnh và yêu cầu", "Phân tích chuyên môn", "Giải pháp và lộ trình"],
            "suggested_custom_fields": [],
            "data_requirements": "Dữ liệu đầu vào, tài liệu nghiệp vụ và tiêu chí đánh giá có thể kiểm chứng.",
            "research_requirements": "Ưu tiên tài liệu chính thức, tiêu chuẩn ngành và nguồn chuyên môn có xuất xứ rõ ràng.",
        }

    @classmethod
    def _mock_market_outline(cls, prompt: str) -> Dict[str, Any]:
        title = cls._prompt_value(prompt, ["TIÊU ĐỀ", "TIEU DE"]) or "Nghiên cứu thị trường"
        outline = [
            {"title": "TÓM TẮT ĐIỀU HÀNH", "level": 1, "position": 1, "children": []},
            {"title": "CHƯƠNG 1: PHẠM VI VÀ PHƯƠNG PHÁP NGHIÊN CỨU", "level": 1, "position": 2, "children": [
                {"title": "1.1 Mục tiêu, phạm vi và câu hỏi nghiên cứu", "level": 2, "position": 1, "children": []},
                {"title": "1.2 Phương pháp và giới hạn dữ liệu", "level": 2, "position": 2, "children": []},
            ]},
            {"title": "CHƯƠNG 2: QUY MÔ VÀ XU HƯỚNG THỊ TRƯỜNG", "level": 1, "position": 3, "children": [
                {"title": "2.1 Động lực tăng trưởng và bối cảnh chính sách", "level": 2, "position": 1, "children": []},
                {"title": "2.2 Hạ tầng, chuỗi cung ứng và rào cản thị trường", "level": 2, "position": 2, "children": []},
            ]},
            {"title": "CHƯƠNG 3: KHÁCH HÀNG, PHÂN KHÚC VÀ CẠNH TRANH", "level": 1, "position": 4, "children": [
                {"title": "3.1 Nhu cầu và tiêu chí lựa chọn của khách hàng", "level": 2, "position": 1, "children": []},
                {"title": "3.2 Bản đồ cạnh tranh và khoảng trống thị trường", "level": 2, "position": 2, "children": []},
            ]},
            {"title": "CHƯƠNG 4: CHIẾN LƯỢC THÂM NHẬP THỊ TRƯỜNG", "level": 1, "position": 5, "children": [
                {"title": "4.1 Định vị giá trị và mô hình tiếp cận khách hàng", "level": 2, "position": 1, "children": []},
                {"title": "4.2 Lộ trình triển khai, KPI và quản trị rủi ro", "level": 2, "position": 2, "children": []},
            ]},
            {"title": "KẾT LUẬN VÀ KIẾN NGHỊ", "level": 1, "position": 6, "children": []},
            {"title": "TÀI LIỆU THAM KHẢO", "level": 1, "position": 7, "children": []},
        ]
        return {
            "project_understanding": f"Báo cáo đánh giá có căn cứ cho đề tài {title}.",
            "objectives": ["Đánh giá quy mô và xu hướng", "Phân tích khách hàng và cạnh tranh", "Đề xuất chiến lược thâm nhập"],
            "scope": "Tập trung vào thị trường, khách hàng, đối thủ, chính sách, hạ tầng và khả năng triển khai chiến lược.",
            "suggested_methodology": "Nghiên cứu thứ cấp có kiểm chứng, phân tích cạnh tranh và tổng hợp chiến lược.",
            "outline": outline,
        }

    def _mock_academic_fallback(self, prompt: str, response_format: Optional[str]) -> Dict[str, Any]:
        """Offline fallback ensuring complete testability and seamless demo execution."""
        if "CHẾ ĐỘ COPILOT CHAT: ANSWER_ONLY" in prompt or "CHE DO COPILOT CHAT: ANSWER_ONLY" in prompt:
            return {
                "text": self._mock_copilot_chat_fallback(prompt),
                "is_demo": True,
                "tokens_used": 180,
                "provider": "gemini",
                "model": "gemini-2.5-flash"
            }

        if response_format == "json" and "Ý TƯỞNG CỦA NGƯỜI DÙNG:" in prompt:
            intent = (
                self._mock_market_intent(prompt)
                if self._use_market_intent_fallback(prompt)
                else self._mock_general_intent(prompt)
            )
            return {
                "text": json.dumps(intent, ensure_ascii=False, indent=2),
                "is_demo": True,
                "tokens_used": 300,
                "provider": "gemini",
                "model": "gemini-2.5-flash",
            }

        if response_format == "json" and "LOẠI TÀI LIỆU:" in prompt and self._use_market_outline_fallback(prompt):
            return {
                "text": json.dumps(self._mock_market_outline(prompt), ensure_ascii=False, indent=2),
                "is_demo": True,
                "tokens_used": 500,
                "provider": "gemini",
                "model": "gemini-2.5-flash",
            }

        if response_format == "json" or "outline" in prompt.lower():
            mock_data = {
                "project_understanding": "Đề tài tập trung vào việc nghiên cứu, phân tích, thiết kế kiến trúc hệ thống và xây dựng ứng dụng thực tế theo các chuẩn kỹ thuật chuyên nghiệp.",
                "objectives": [
                    "Nghiên cứu cơ sở lý thuyết và các công nghệ nền tảng liên quan.",
                    "Phân tích yêu cầu chức năng và phi chức năng của hệ thống.",
                    "Thiết kế kiến trúc hệ thống, cơ sở dữ liệu và các luồng xử lý chính.",
                    "Hiện thực hóa mã nguồn và tích hợp các module chức năng.",
                    "Thực nghiệm, đánh giá hiệu năng và kiểm thử toàn diện hệ thống."
                ],
                "scope": "Phạm vi đề tài bao gồm phân tích nghiệp vụ, thiết kế kiến trúc, cài đặt ứng dụng và kiểm thử tính năng hoàn chỉnh.",
                "suggested_methodology": "Áp dụng phương pháp nghiên cứu kết hợp thực nghiệm (Experimental Research) và mô hình phát triển phần mềm lặp Agile/Scrum.",
                "outline": [
                    {
                        "title": "LỜI MỞ ĐẦU",
                        "level": 1,
                        "position": 1,
                        "section_number": "",
                        "description": "Giới thiệu bối cảnh, tính cấp thiết và lý do chọn đề tài.",
                        "children": []
                    },
                    {
                        "title": "CHƯƠNG 1: TỔNG QUAN VỀ ĐỀ TÀI",
                        "level": 1,
                        "position": 2,
                        "section_number": "1",
                        "description": "Bối cảnh, mục tiêu, đối tượng, phạm vi nghiên cứu và phương pháp thực hiện.",
                        "children": [
                            {"title": "1.1 Bối cảnh và lý do chọn đề tài", "level": 2, "position": 1, "section_number": "1.1", "description": "", "children": []},
                            {"title": "1.2 Mục tiêu nghiên cứu", "level": 2, "position": 2, "section_number": "1.2", "description": "", "children": []},
                            {"title": "1.3 Phạm vi và đối tượng nghiên cứu", "level": 2, "position": 3, "section_number": "1.3", "description": "", "children": []},
                            {"title": "1.4 Phương pháp thực hiện và cấu trúc báo cáo", "level": 2, "position": 4, "section_number": "1.4", "description": "", "children": []}
                        ]
                    },
                    {
                        "title": "CHƯƠNG 2: CƠ SỞ LÝ THUYẾT VÀ CÔNG NGHỆ SỬ DỤNG",
                        "level": 1,
                        "position": 3,
                        "section_number": "2",
                        "description": "Trình bày các framework, kiến trúc và công nghệ cốt lõi.",
                        "children": [
                            {"title": "2.1 Tổng quan về kiến trúc nền tảng", "level": 2, "position": 1, "section_number": "2.1", "description": "", "children": []},
                            {"title": "2.2 Các công nghệ và thư viện chủ chốt", "level": 2, "position": 2, "section_number": "2.2", "description": "", "children": []},
                            {"title": "2.3 Cơ chế xác thực và bảo mật", "level": 2, "position": 3, "section_number": "2.3", "description": "", "children": []},
                            {"title": "2.4 So sánh và đánh giá các giải pháp công nghệ", "level": 2, "position": 4, "section_number": "2.4", "description": "", "children": []}
                        ]
                    },
                    {
                        "title": "CHƯƠNG 3: PHÂN TÍCH VÀ THIẾT KẾ HỆ THỐNG",
                        "level": 1,
                        "position": 4,
                        "section_number": "3",
                        "description": "Đặc tả yêu cầu, Use Case, thiết kế cơ sở dữ liệu và kiến trúc.",
                        "children": [
                            {"title": "3.1 Phân tích yêu cầu chức năng và phi chức năng", "level": 2, "position": 1, "section_number": "3.1", "description": "", "children": []},
                            {"title": "3.2 Thiết kế sơ đồ Use Case và luồng nghiệp vụ", "level": 2, "position": 2, "section_number": "3.2", "description": "", "children": []},
                            {"title": "3.3 Thiết kế cơ sở dữ liệu và lược đồ quan hệ (ERD)", "level": 2, "position": 3, "section_number": "3.3", "description": "", "children": []},
                            {"title": "3.4 Thiết kế kiến trúc phần mềm và tương tác module", "level": 2, "position": 4, "section_number": "3.4", "description": "", "children": []}
                        ]
                    },
                    {
                        "title": "CHƯƠNG 4: HIỆN THỰC HÓA VÀ KẾT QUẢ TRIỂN KHAI",
                        "level": 1,
                        "position": 5,
                        "section_number": "4",
                        "description": "Chi tiết triển khai mã nguồn, giao diện và các tính năng chính.",
                        "children": [
                            {"title": "4.1 Triển khai cấu trúc module và dịch vụ lõi", "level": 2, "position": 1, "section_number": "4.1", "description": "", "children": []},
                            {"title": "4.2 Hiện thực hóa các tính năng nghiệp vụ chính", "level": 2, "position": 2, "section_number": "4.2", "description": "", "children": []},
                            {"title": "4.3 Giao diện người dùng và trải nghiệm tương tác", "level": 2, "position": 3, "section_number": "4.3", "description": "", "children": []}
                        ]
                    },
                    {
                        "title": "CHƯƠNG 5: KIỂM THỬ VÀ ĐÁNH GIÁ KẾT QUẢ",
                        "level": 1,
                        "position": 6,
                        "section_number": "5",
                        "description": "Kế hoạch kiểm thử, kết quả kiểm thử chức năng và hiệu năng.",
                        "children": [
                            {"title": "5.1 Môi trường và kịch bản kiểm thử", "level": 2, "position": 1, "section_number": "5.1", "description": "", "children": []},
                            {"title": "5.2 Kết quả kiểm thử chức năng và phi chức năng", "level": 2, "position": 2, "section_number": "5.2", "description": "", "children": []}
                        ]
                    },
                    {
                        "title": "CHƯƠNG 6: KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN",
                        "level": 1,
                        "position": 7,
                        "section_number": "6",
                        "description": "Tổng kết kết quả đạt được, hạn chế và định hướng phát triển tương lai.",
                        "children": [
                            {"title": "6.1 Các kết quả đạt được của đề tài", "level": 2, "position": 1, "section_number": "6.1", "description": "", "children": []},
                            {"title": "6.2 Hạn chế và hướng phát triển mở rộng", "level": 2, "position": 2, "section_number": "6.2", "description": "", "children": []}
                        ]
                    },
                    {
                        "title": "TÀI LIỆU THAM KHẢO",
                        "level": 1,
                        "position": 8,
                        "section_number": "",
                        "description": "Danh mục các tài liệu và bài báo khoa học được trích dẫn theo chuẩn IEEE.",
                        "children": []
                    }
                ]
            }
            return {
                "text": json.dumps(mock_data, ensure_ascii=False, indent=2),
                "is_demo": True,
                "tokens_used": 650,
                "provider": "gemini",
                "model": "gemini-2.5-flash"
            }

        return {
            "text": self._mock_section_fallback(prompt),
            "is_demo": True,
                "tokens_used": 1800,
            "provider": "gemini",
            "model": "gemini-2.5-flash"
        }

    def _mock_section_fallback(self, prompt: str) -> str:
        """Generate a usable long-form section when the live Gemini API is unavailable."""
        section_title = "Mục báo cáo"
        topic_name = "đề tài nghiên cứu"

        for marker in ["MỤC ĐANG SOẠN THẢO:", "MUC DANG SOAN THAO:", "MỤC ĐANG VIẾT:", "MUC DANG VIET:"]:
            if marker in prompt:
                section_title = prompt.split(marker, 1)[1].splitlines()[0].strip()
                section_title = re.split(r"\((?:Cấp độ|Heading)", section_title, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                break

        for marker in ["ĐỀ TÀI BÁO CÁO:", "DE TAI BAO CAO:", "ĐỀ TÀI:", "DE TAI:"]:
            if marker in prompt:
                topic_name = prompt.split(marker, 1)[1].splitlines()[0].strip()
                break

        target_words = 900
        lowered = prompt.lower()
        for unit in ["từ", "tu"]:
            if unit in lowered:
                match = re.search(r"(\d{3,5})\s*(?:từ|tu)", lowered)
                if match:
                    target_words = max(180, min(int(match.group(1)), 1200))
                    break

        evidence = re.findall(
            r"\[SRC:([^\]]+)\]\s+([^\n]+)\nURL:\s*[^\n]*\nBằng chứng:\s*([^\n]+)",
            prompt or "",
            flags=re.IGNORECASE,
        )
        if evidence:
            return self._mock_grounded_section_text(
                section_title,
                topic_name,
                target_words,
                evidence,
            )
        return self._mock_section_text(section_title, topic_name, target_words)

    def _mock_grounded_section_text(
        self,
        section_title: str,
        topic_name: str,
        target_words: int,
        evidence: List[tuple[str, str, str]],
    ) -> str:
        title = section_title.strip() or "Mục báo cáo"
        topic = " ".join((topic_name or "đề tài nghiên cứu").split()).strip()
        safe_topic = self._without_specific_values(topic) or "đề tài đã nêu"
        safe_title = self._without_specific_values(title) or "mục báo cáo"
        paragraphs = [
            safe_title,
            f"Mục này phân tích \"{safe_topic}\" trong phạm vi {safe_title.lower()}. Các nhận định dưới đây được giới hạn theo những nguồn đã thu thập và cần được đọc cùng thời điểm công bố của từng tài liệu.",
        ]
        for source_id, source_title, excerpt in evidence[:4]:
            clean_excerpt = re.sub(r"\s+", " ", excerpt).strip()
            cited_excerpt = self._cite_each_sentence(clean_excerpt, source_id)
            paragraphs.append(
                f"Nguồn \"{source_title.strip()}\" ghi nhận rằng {cited_excerpt}"
            )
        paragraphs.extend([
            "Các bằng chứng cho phép xác định hướng vận động và những yếu tố cần ưu tiên, nhưng chưa đủ để suy rộng cho toàn bộ thị trường nếu thiếu dữ liệu định lượng đồng nhất giữa các nguồn.",
            f"Đối với {safe_title.lower()}, cách sử dụng phù hợp là đối chiếu các nguồn, tách dữ kiện đã kiểm chứng khỏi nhận định chiến lược và cập nhật kết luận khi có số liệu mới.",
        ])
        dimensions = [
            "nhu cầu và hành vi của nhóm sử dụng mục tiêu",
            "cấu trúc cạnh tranh và khả năng tạo khác biệt",
            "điều kiện hạ tầng và năng lực cung ứng",
            "khung chính sách và yêu cầu tuân thủ",
            "chi phí triển khai và hiệu quả nguồn lực",
            "khả năng tiếp cận và duy trì khách hàng",
            "rủi ro vận hành và phương án ứng phó",
            "năng lực của các đối tác trong chuỗi giá trị",
            "mức độ sẵn sàng của tổ chức thực hiện",
            "cơ chế theo dõi kết quả và cập nhật quyết định",
        ]
        approaches = [
            "đối chiếu các dấu hiệu đồng thuận và khác biệt giữa những nguồn đã thu thập",
            "phân biệt dữ kiện quan sát được với giả định cần tiếp tục kiểm chứng",
            "xem xét mối liên hệ giữa bối cảnh bên ngoài và năng lực triển khai nội bộ",
            "đánh giá tác động trước mắt cùng hệ quả có thể xuất hiện trong quá trình thực hiện",
            "xác định điều kiện cần có trước khi chuyển nhận định thành quyết định",
            "ghi rõ giới hạn dữ liệu để tránh suy rộng vượt quá phạm vi bằng chứng",
        ]
        implications = [
            "ưu tiên kiểm tra chéo trước khi lựa chọn phương án hành động",
            "xây dựng tiêu chí theo dõi có thể cập nhật khi xuất hiện thông tin mới",
            "giữ các kiến nghị gắn với nguồn lực và điều kiện thực hiện thực tế",
            "tách rõ kết luận đã có căn cứ khỏi vấn đề còn cần khảo sát bổ sung",
            "xem xét nhiều kịch bản thay vì phụ thuộc vào một giả định duy nhất",
        ]
        text = "\n\n".join(paragraphs)
        index = 0
        while len(text.split()) < target_words and index < len(dimensions) * len(approaches):
            source_id = evidence[index % len(evidence)][0]
            dimension = dimensions[index % len(dimensions)]
            approach = approaches[(index // len(dimensions)) % len(approaches)]
            implication = implications[index % len(implications)]
            text += "\n\n" + (
                f"Xét theo {dimension}, phần phân tích cần {approach}. "
                f"Trong phạm vi {safe_title.lower()}, cách đọc này giúp nhận diện yếu tố có thể tác động đến kết quả, "
                f"đồng thời buộc lập luận phải {implication}. "
                f"Bằng chứng liên quan được dùng làm điểm tựa cho bước đối chiếu này [SRC:{source_id}]."
            )
            index += 1
        return text

    @staticmethod
    def _without_specific_values(value: str) -> str:
        cleaned = re.sub(r"\b(?:năm\s*)?(?:19|20)\d{2}\b", "", value or "", flags=re.IGNORECASE)
        cleaned = re.sub(r"\d+(?:[.,]\d+)?\s*%", "", cleaned)
        cleaned = re.sub(
            r"\b\d+(?:[.,]\d+)?\s*(?:triệu|tỷ|nghìn|USD|VND)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\(\s*\)|\[\s*\]", "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip(" ,;:-–—")

    @staticmethod
    def _cite_each_sentence(value: str, source_id: str) -> str:
        cited_sentences: List[str] = []
        for sentence in re.split(r"(?<=[.!?。])\s+", value or ""):
            cleaned = sentence.strip()
            if not cleaned:
                continue
            marker = f"[SRC:{source_id}]"
            if marker in cleaned:
                cited_sentences.append(cleaned)
                continue
            punctuation = re.search(r"([.!?。]+)$", cleaned)
            if punctuation:
                cited_sentences.append(
                    f"{cleaned[:punctuation.start()].rstrip()} {marker}{punctuation.group(1)}"
                )
            else:
                cited_sentences.append(f"{cleaned} {marker}.")
        return " ".join(cited_sentences)

    def _mock_section_text(self, section_title: str, topic_name: str, target_words: int) -> str:
        title = section_title.strip() or "Mục báo cáo"
        topic = " ".join((topic_name or "đề tài nghiên cứu").split()).strip()
        upper = title.upper()
        stripped = __import__("re").sub(r"^\d+(?:\.\d+){1,2}\s*", "", title).strip()
        if stripped != title:
            specific = self._mock_numbered_section_text(title, stripped, topic)
            if specific:
                return specific

        if upper.startswith("LỜI"):
            paragraphs = [
                f"Đề tài \"{topic}\" được thực hiện nhằm hệ thống hóa kiến thức nền tảng và làm rõ cách các thành phần kỹ thuật phối hợp trong một hệ thống hoàn chỉnh.",
                "Báo cáo tiếp cận vấn đề theo hướng học thuật kết hợp thực tiễn: trình bày cơ sở lý thuyết, phân tích yêu cầu, mô tả thiết kế, triển khai và đánh giá kết quả.",
                "Nội dung được tổ chức để người đọc có thể theo dõi từ bối cảnh hình thành đề tài đến kết quả đạt được, đồng thời nhận diện các hạn chế còn cần tiếp tục cải thiện.",
            ]
        elif "TỔNG QUAN" in upper or "BỐI CẢNH" in upper:
            paragraphs = [
                f"Chương tổng quan đặt nền tảng cho đề tài \"{topic}\" bằng cách xác định lý do chọn đề tài, mục tiêu nghiên cứu, phạm vi thực hiện và phương pháp tiếp cận.",
                "Trọng tâm của chương là làm rõ vấn đề cần giải quyết, đối tượng được khảo sát và giá trị thực tiễn của kết quả nghiên cứu.",
                "| Nội dung | Vai trò |\n|---|---|\n| Bối cảnh | Giải thích nhu cầu nghiên cứu |\n| Mục tiêu | Xác định kết quả cần đạt |\n| Phạm vi | Giới hạn nội dung triển khai |",
            ]
        elif "CƠ SỞ" in upper or "LÝ THUYẾT" in upper or "CÔNG NGHỆ" in upper:
            paragraphs = [
                "Chương này trình bày các khái niệm và công nghệ nền tảng phục vụ quá trình phân tích và triển khai hệ thống.",
                "Các thành phần như bộ xử lý, bộ nhớ, lưu trữ, mạng, hệ điều hành và phần mềm ứng dụng cần được xem xét trong quan hệ tương tác thay vì tách rời.",
                "| Thành phần | Vai trò | Tác động |\n|---|---|---|\n| CPU | Xử lý tính toán | Ảnh hưởng tốc độ thực thi |\n| RAM | Lưu dữ liệu tạm | Ảnh hưởng độ trễ |\n| Mạng | Truyền thông | Ảnh hưởng thông lượng |",
            ]
        elif "PHÂN TÍCH" in upper or "THIẾT KẾ" in upper or "YÊU CẦU" in upper:
            paragraphs = [
                "Phần phân tích và thiết kế chuyển mục tiêu nghiên cứu thành yêu cầu cụ thể, từ đó xây dựng mô hình hệ thống có thể triển khai.",
                "Cần phân biệt yêu cầu chức năng với yêu cầu phi chức năng như hiệu năng, bảo mật, độ tin cậy và khả năng mở rộng.",
                "[[IMAGE:title=Sơ đồ thiết kế hệ thống;prompt=Sơ đồ kiến trúc gồm giao diện, API, cơ sở dữ liệu, lưu trữ và giám sát]]",
            ]
        elif "TRIỂN KHAI" in upper or "CÀI ĐẶT" in upper or "CẤU HÌNH" in upper:
            paragraphs = [
                "Phần triển khai mô tả các bước chuẩn bị môi trường, cài đặt phần mềm, cấu hình dịch vụ và đưa hệ thống vào trạng thái vận hành.",
                "Một quy trình triển khai tốt cần có kiểm tra sau cài đặt, ghi log, sao lưu cấu hình và phương án phục hồi khi dịch vụ gặp sự cố.",
                "| Giai đoạn | Kết quả cần đạt |\n|---|---|\n| Chuẩn bị | Môi trường sẵn sàng |\n| Cấu hình | Dịch vụ chạy đúng |\n| Kiểm tra | Xác nhận hệ thống hoạt động |",
            ]
        elif "KIỂM THỬ" in upper or "ĐÁNH GIÁ" in upper or "HIỆU NĂNG" in upper:
            paragraphs = [
                "Phần kiểm thử đánh giá mức độ đáp ứng của hệ thống so với yêu cầu ban đầu thông qua các tiêu chí có thể đo lường.",
                "Các chỉ số quan trọng gồm thời gian phản hồi, thông lượng, mức sử dụng tài nguyên, tỷ lệ lỗi và khả năng phục hồi.",
                "[[CHART:type=bar;title=Mức đáp ứng tiêu chí kiểm thử;labels=Chức năng,Hiệu năng,Bảo mật,Ổn định;values=88,80,76,84;unit=%]]",
            ]
        elif "KẾT LUẬN" in upper:
            paragraphs = [
                f"Báo cáo đã hoàn thành việc phân tích các nội dung trọng tâm của đề tài \"{topic}\" và chỉ ra mối quan hệ giữa cơ sở lý thuyết, thiết kế, triển khai và đánh giá.",
                "Kết quả cho thấy chất lượng hệ thống phụ thuộc vào sự cân bằng giữa kiến trúc, cấu hình, tài nguyên, bảo mật và quy trình vận hành.",
                "Hướng phát triển tiếp theo là bổ sung thêm dữ liệu đo kiểm, mở rộng kịch bản thử nghiệm và tối ưu các điểm còn hạn chế.",
            ]
        else:
            paragraphs = [
                f"Mục \"{title}\" làm rõ một nội dung cụ thể trong đề tài \"{topic}\" và cần được trình bày theo đúng vai trò của nó trong cấu trúc báo cáo.",
                "Nội dung nên đi từ khái niệm đến phân tích, sau đó liên hệ với điều kiện triển khai hoặc minh chứng thực tế.",
                "Cách trình bày này giúp báo cáo mạch lạc hơn và tránh lặp lại nguyên văn các chương mục khác.",
            ]

        text = f"{title}\n\n" + "\n\n".join(paragraphs)
        additions = [
            "Về mặt thực tiễn, nội dung cần được gắn với điều kiện sử dụng cụ thể để các nhận xét có giá trị áp dụng.",
            "Về mặt kỹ thuật, mỗi lựa chọn cần được đánh giá theo hiệu năng, chi phí, độ ổn định và khả năng mở rộng.",
            "Về mặt trình bày, phần này cần kết thúc bằng nhận định rõ để liên kết với phần tiếp theo của báo cáo.",
        ]
        i = 0
        while len(text.split()) < target_words and i < len(additions) * 3:
            text += "\n\n" + additions[i % len(additions)]
            i += 1
        return text

    def _mock_numbered_section_text(self, title: str, stripped_title: str, topic: str) -> str:
        upper = stripped_title.upper()
        topic_lower = topic.lower()
        is_arm_x86 = "arm" in topic_lower and "x86" in topic_lower

        if "MỤC TIÊU" in upper:
            return (
                f"{title}\n\n"
                f"Mục tiêu của đề tài \"{topic}\" là làm rõ sự khác biệt giữa các kiến trúc xử lý ở cả góc độ nguyên lý và ứng dụng thực tế. Nội dung không chỉ nêu khái niệm mà còn xác định các tiêu chí đánh giá có thể sử dụng khi lựa chọn nền tảng cho một hệ thống máy tính hiện đại.\n\n"
                "Các mục tiêu cụ thể gồm: phân tích đặc điểm kiến trúc, đánh giá hiệu năng, xem xét mức tiêu thụ năng lượng, so sánh khả năng tương thích phần mềm và nhận diện bối cảnh ứng dụng phù hợp. Nhờ đó, báo cáo có thể đưa ra nhận xét có căn cứ thay vì kết luận cảm tính.\n\n"
                "| Nhóm mục tiêu | Nội dung cần đạt |\n|---|---|\n| Kiến thức | Hiểu nguyên lý kiến trúc và tổ chức xử lý |\n| So sánh | Đánh giá theo hiệu năng, điện năng và tương thích |\n| Ứng dụng | Đề xuất bối cảnh sử dụng phù hợp |\n\n"
                "Kết quả mong muốn là người đọc hiểu vì sao cùng là bộ xử lý nhưng ARM và x86 có lợi thế khác nhau trong từng môi trường như máy tính cá nhân, thiết bị di động, hệ thống nhúng, máy chủ và nền tảng điện toán đám mây."
            )
        if "PHẠM VI" in upper or "ĐỐI TƯỢNG" in upper:
            arm_detail = "Với ARM, báo cáo chú ý đến thiết kế tiết kiệm năng lượng, SoC và xu hướng mở rộng sang laptop/máy chủ. Với x86, báo cáo tập trung vào hiệu năng truyền thống, khả năng tương thích và hệ sinh thái phần mềm lâu đời." if is_arm_x86 else "Báo cáo tập trung vào các thành phần và tiêu chí có ảnh hưởng trực tiếp đến quá trình thiết kế, triển khai và đánh giá hệ thống."
            return (
                f"{title}\n\n"
                f"Phạm vi nghiên cứu của mục này được giới hạn trong các yếu tố có liên quan trực tiếp đến đề tài \"{topic}\". Nội dung xem xét khía cạnh kiến trúc, môi trường vận hành, phần mềm hỗ trợ, tiêu chí hiệu năng và điều kiện triển khai trong thực tế.\n\n"
                f"{arm_detail}\n\n"
                "| Nội dung | Phạm vi xem xét |\n|---|---|\n| Kiến trúc | Tập lệnh, tổ chức xử lý, bộ nhớ và cache |\n| Hệ thống | Máy tính cá nhân, máy chủ, thiết bị nhúng và cloud |\n| Giới hạn | Không đi sâu vào thiết kế transistor hoặc benchmark ngoài phạm vi môn học |\n\n"
                "Việc xác định rõ phạm vi giúp các chương sau có trọng tâm hơn. Các nhận xét được đặt trong điều kiện sử dụng phổ biến, không khẳng định tuyệt đối cho mọi dòng phần cứng hoặc mọi nhà sản xuất."
            )
        if "PHƯƠNG PHÁP" in upper or "CẤU TRÚC" in upper:
            return (
                f"{title}\n\n"
                "Phương pháp thực hiện được xây dựng theo hướng tổng hợp tài liệu, phân tích kiến trúc và so sánh theo tiêu chí. Trước hết, báo cáo hệ thống hóa các khái niệm nền tảng để tạo cơ sở chung cho việc đánh giá.\n\n"
                "Sau đó, từng tiêu chí như hiệu năng, điện năng, khả năng tương thích, chi phí và khả năng mở rộng được sử dụng để phân tích. Cách tiếp cận này giúp nội dung giữ được sự cân bằng giữa lý thuyết và ứng dụng.\n\n"
                "Cấu trúc báo cáo đi từ tổng quan đến cơ sở lý thuyết, từ phân tích so sánh đến đánh giá và kết luận. Trình tự này giúp người đọc theo dõi được mạch lập luận và thấy rõ cơ sở của từng nhận xét."
            )
        if "BỐI CẢNH" in upper or "LÝ DO" in upper:
            return (
                f"{title}\n\n"
                f"Bối cảnh nghiên cứu của đề tài \"{topic}\" xuất phát từ sự thay đổi nhanh của hệ thống máy tính hiện đại. Các nền tảng phần cứng ngày nay không chỉ cạnh tranh về tốc độ xử lý mà còn về điện năng, khả năng tích hợp, độ ổn định và hệ sinh thái phần mềm.\n\n"
                "Trong bối cảnh đó, việc hiểu rõ đặc điểm của từng kiến trúc giúp người học có cơ sở lựa chọn giải pháp phù hợp. Một kiến trúc mạnh trong máy chủ truyền thống chưa chắc tối ưu cho thiết bị tiết kiệm điện, và một kiến trúc tiết kiệm năng lượng cũng cần được đánh giá về khả năng tương thích phần mềm.\n\n"
                "Vì vậy, đề tài có ý nghĩa cả về mặt học thuật lẫn thực tiễn, đặc biệt khi các xu hướng như cloud, edge computing, thiết bị di động và máy tính cá nhân hiệu năng cao đang phát triển song song."
            )
        return None

    def _mock_copilot_chat_fallback(self, prompt: str) -> str:
        question = ""
        if "CÂU HỎI CỦA NGƯỜI DÙNG:" in prompt:
            question = prompt.split("CÂU HỎI CỦA NGƯỜI DÙNG:", 1)[1].split("NGỮ CẢNH DỰ ÁN:", 1)[0].strip().strip('"')
        project_topic = ""
        for line in prompt.splitlines():
            if line.startswith("- Đề tài/dự án:"):
                project_topic = line.split(":", 1)[1].strip()
                break

        lowered = question.lower()
        if any(term in lowered for term in ["đề tài", "chủ đề", "tên báo cáo", "tôi đang làm"]):
            return f"Đề tài hiện tại của bạn là: **{project_topic or 'chưa có tên đề tài trong dữ liệu dự án'}**."
        if any(term in lowered for term in ["tác dụng", "để làm gì", "là gì"]):
            return "Phần này dùng để hỗ trợ bạn hỏi đáp về dự án và điều khiển AI viết/sửa nội dung khi có yêu cầu rõ ràng."
        if any(term in lowered for term in ["không hoạt động", "lỗi", "sao"]):
            return "Có thể chức năng đang thiếu dữ liệu ngữ cảnh hoặc chưa nhận đúng ý định. Bạn mô tả thao tác cụ thể, mình sẽ kiểm tra đúng phần đó."
        return "Mình hiểu. Bạn có thể hỏi trực tiếp về dự án, nội dung đang chọn, hoặc yêu cầu rõ nếu muốn mình viết/sửa/chèn vào tài liệu."
