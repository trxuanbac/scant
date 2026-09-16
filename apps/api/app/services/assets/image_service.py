import hashlib
import ipaddress
import os
import socket
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import ImageAsset


ALLOWED_IMAGE_MIME_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_IMAGE_SIZE = 12 * 1024 * 1024


class ImageValidationError(ValueError):
    pass


class ImageService:
    def detect_image_type(self, data: bytes) -> Tuple[str, str]:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png", ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg", ".jpg"
        if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            return "image/gif", ".gif"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp", ".webp"
        raise ImageValidationError("File không phải ảnh PNG, JPG, WEBP hoặc GIF hợp lệ.")

    def read_dimensions(self, data: bytes, mime_type: str) -> Tuple[Optional[int], Optional[int]]:
        try:
            if mime_type == "image/png" and len(data) >= 24:
                return struct.unpack(">II", data[16:24])
            if mime_type == "image/gif" and len(data) >= 10:
                return struct.unpack("<HH", data[6:10])
            if mime_type == "image/jpeg":
                return self._jpeg_dimensions(data)
            if mime_type == "image/webp":
                return self._webp_dimensions(data)
        except Exception:
            return None, None
        return None, None

    def _jpeg_dimensions(self, data: bytes) -> Tuple[Optional[int], Optional[int]]:
        idx = 2
        while idx < len(data) - 9:
            if data[idx] != 0xFF:
                idx += 1
                continue
            marker = data[idx + 1]
            idx += 2
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(data[idx + 3: idx + 5], "big")
                width = int.from_bytes(data[idx + 5: idx + 7], "big")
                return width, height
            block_len = int.from_bytes(data[idx: idx + 2], "big")
            idx += max(block_len, 2)
        return None, None

    def _webp_dimensions(self, data: bytes) -> Tuple[Optional[int], Optional[int]]:
        if len(data) < 30:
            return None, None
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return width, height
        if chunk == b"VP8 " and len(data) >= 30:
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
            return width, height
        if chunk == b"VP8L" and len(data) >= 25:
            bits = int.from_bytes(data[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return width, height
        return None, None

    def validate_image(self, data: bytes) -> Tuple[str, str, Optional[int], Optional[int], str]:
        if not data:
            raise ImageValidationError("Ảnh rỗng.")
        if len(data) > MAX_IMAGE_SIZE:
            raise ImageValidationError("Ảnh vượt quá giới hạn 12MB.")
        mime_type, ext = self.detect_image_type(data)
        width, height = self.read_dimensions(data, mime_type)
        checksum = hashlib.sha256(data).hexdigest()
        return mime_type, ext, width, height, checksum

    async def create_asset(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        report_id: Optional[str],
        user_id: Optional[str],
        file_name: str,
        data: bytes,
        source_type: str,
        original_url: Optional[str] = None,
        source_page_url: Optional[str] = None,
        source_title: Optional[str] = None,
        license_value: Optional[str] = None,
        attribution: Optional[str] = None,
    ) -> ImageAsset:
        mime_type, ext, width, height, checksum = self.validate_image(data)

        existing = await db.execute(
            select(ImageAsset).where(
                ImageAsset.project_id == project_id,
                ImageAsset.checksum_sha256 == checksum,
            )
        )
        duplicate = existing.scalars().first()
        if duplicate:
            return duplicate

        safe_name = Path(file_name or "image").stem[:80].replace("/", "_").replace("\\", "_")
        stored_name = f"{project_id}_{checksum[:16]}_{safe_name}{ext}"
        asset_dir = settings.ASSETS_DIR / project_id
        asset_dir.mkdir(parents=True, exist_ok=True)
        storage_path = asset_dir / stored_name
        storage_path.write_bytes(data)

        parsed = urlparse(original_url or source_page_url or "")
        source_domain = parsed.netloc.lower() or None

        asset = ImageAsset(
            project_id=project_id,
            report_id=report_id,
            user_id=user_id,
            file_name=f"{safe_name}{ext}",
            mime_type=mime_type,
            file_size=len(data),
            width=width,
            height=height,
            storage_path=str(storage_path),
            thumbnail_path=None,
            checksum_sha256=checksum,
            source_type=source_type,
            original_url=original_url,
            source_domain=source_domain,
            source_title=source_title,
            source_page_url=source_page_url,
            license=license_value,
            attribution=attribution,
            metadata_json={"optimized": False, "thumbnail": False},
        )
        db.add(asset)
        await db.commit()
        await db.refresh(asset)
        return asset

    def assert_safe_remote_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ImageValidationError("Chỉ hỗ trợ URL http/https.")
        hostname = parsed.hostname
        if not hostname:
            raise ImageValidationError("URL ảnh không hợp lệ.")
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            raise ImageValidationError("Không thể phân giải domain ảnh.") from exc
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ImageValidationError("URL ảnh trỏ tới mạng nội bộ hoặc địa chỉ bị chặn.")

    async def download_remote_image(self, url: str) -> Tuple[bytes, str]:
        self.assert_safe_remote_url(url)
        timeout = httpx.Timeout(8.0, connect=4.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, max_redirects=3) as client:
            response = await client.get(url, headers={"User-Agent": "AIReportStudioImageImporter/1.0"})
            response.raise_for_status()
            final_url = str(response.url)
            self.assert_safe_remote_url(final_url)
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            data = response.content
            mime_type, _, _, _, _ = self.validate_image(data)
            if content_type and content_type not in ALLOWED_IMAGE_MIME_TYPES:
                raise ImageValidationError("Content-Type không phải ảnh hợp lệ.")
            return data, final_url

    async def search_web_images(self, query: str, license_mode: str = "all", max_results: int = 12) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "q": query,
            "page_size": min(max_results, 24),
            "mature": "false",
        }
        if license_mode in {"creative_commons", "free_to_use", "stock_free"}:
            params["license_type"] = "commercial"

        payload: Dict[str, Any] = {}
        failures: List[str] = []
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            for endpoint in (
                "https://api.openverse.org/v1/images/",
                "https://api.openverse.engineering/v1/images/",
            ):
                try:
                    response = await client.get(endpoint, params=params, headers={"User-Agent": "AIReportStudio/1.0"})
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("results") is not None:
                        break
                except Exception as exc:
                    failures.append(f"{urlparse(endpoint).netloc}: {type(exc).__name__}")
        if not payload:
            return {
                "provider": "openverse",
                "results": [],
                "error": "Không kết nối được dịch vụ ảnh Openverse (" + ", ".join(failures) + ").",
            }

        results: List[Dict[str, Any]] = []
        for item in payload.get("results", [])[:max_results]:
            image_url = item.get("url") or item.get("thumbnail")
            thumb = item.get("thumbnail") or image_url
            if not image_url or not thumb:
                continue
            source_page = item.get("foreign_landing_url") or item.get("url")
            parsed = urlparse(source_page or image_url)
            results.append({
                "id": item.get("id") or hashlib.sha1(image_url.encode()).hexdigest(),
                "thumbnailUrl": thumb,
                "imageUrl": image_url,
                "title": item.get("title") or "Ảnh từ Openverse",
                "sourcePageUrl": source_page,
                "sourceDomain": parsed.netloc,
                "width": item.get("width"),
                "height": item.get("height"),
                "license": item.get("license") or item.get("license_version"),
                "attribution": item.get("creator") or item.get("attribution"),
            })
        return {"provider": "openverse", "results": results}

    async def import_search_result(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        report_id: Optional[str],
        user_id: Optional[str],
        result: Dict[str, Any],
    ) -> ImageAsset:
        image_url = str(result.get("imageUrl") or result.get("image_url") or "").strip()
        if not image_url:
            raise ImageValidationError("Kết quả tìm kiếm không có URL ảnh.")
        data, final_url = await self.download_remote_image(image_url)
        return await self.create_asset(
            db,
            project_id=project_id,
            report_id=report_id,
            user_id=user_id,
            file_name=Path(urlparse(image_url).path).name or "web-image",
            data=data,
            source_type="web",
            original_url=final_url,
            source_page_url=str(result.get("sourcePageUrl") or result.get("source_page_url") or "") or None,
            source_title=str(result.get("title") or "") or None,
            license_value=str(result.get("license") or "") or None,
            attribution=str(result.get("attribution") or "") or None,
        )

    def suggest_queries(self, section_title: str, section_text: str, report_title: str, max_queries: int = 6) -> List[str]:
        base = " ".join([report_title, section_title]).strip()
        text = section_text[:400]
        seeds = [
            f"{base} infographic",
            f"{base} diagram",
            f"{base} dashboard",
            f"{base} process chart",
            f"{base} {text[:80]}".strip(),
        ]
        seen = []
        for item in seeds:
            cleaned = " ".join(item.split())
            if len(cleaned) > 4 and cleaned.lower() not in {s.lower() for s in seen}:
                seen.append(cleaned)
        return seen[:max_queries]

    def response_for_asset(self, asset: ImageAsset) -> Dict[str, Any]:
        return {
            "id": asset.id,
            "project_id": asset.project_id,
            "report_id": asset.report_id,
            "file_name": asset.file_name,
            "mime_type": asset.mime_type,
            "file_size": asset.file_size,
            "width": asset.width,
            "height": asset.height,
            "source_type": asset.source_type,
            "original_url": asset.original_url,
            "source_domain": asset.source_domain,
            "source_title": asset.source_title,
            "source_page_url": asset.source_page_url,
            "license": asset.license,
            "attribution": asset.attribution,
            "metadata_json": asset.metadata_json or {},
            "content_url": f"{settings.API_V1_STR}/assets/images/{asset.id}/content",
            "created_at": asset.created_at,
        }


image_service = ImageService()
