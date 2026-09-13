import asyncio
import logging
import hashlib
import re
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse
from app.services.security.ssrf_validator import ssrf_validator
import httpx
from bs4 import BeautifulSoup


class WebScraper:
    """Scrapes, extracts text, cleans metadata, and hashes web content."""

    MAX_RESPONSE_BYTES = 2 * 1024 * 1024
    MAX_REDIRECTS = 4

    @staticmethod
    async def scrape_url(url: str, timeout: float = 15.0) -> Dict[str, Any]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 AIReportStudioBot/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                    target = url
                    for redirect_count in range(WebScraper.MAX_REDIRECTS + 1):
                        safe, reason = await asyncio.to_thread(ssrf_validator.is_url_safe, target)
                        if not safe:
                            raise ValueError("Unsafe research URL")
                        async with client.stream("GET", target, headers=headers) as res:
                            if res.status_code in {301, 302, 303, 307, 308}:
                                location = res.headers.get("location")
                                if not location or redirect_count == WebScraper.MAX_REDIRECTS:
                                    raise ValueError("Invalid or excessive research redirects")
                                target = urljoin(target, location)
                                continue
                            res.raise_for_status()
                            content = bytearray()
                            async for chunk in res.aiter_bytes():
                                content.extend(chunk)
                                if len(content) > WebScraper.MAX_RESPONSE_BYTES:
                                    raise ValueError("Research response exceeds size limit")
                            html = content.decode(res.encoding or "utf-8", errors="replace")
                            break
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            # Failure is not evidence. Do not manufacture authors, dates or excerpts.
            logging.getLogger(__name__).warning("Research fetch unavailable: %s", type(exc).__name__)
            return {
                "title": "", "authors": "", "publisher": "",
                "published_date": "", "extracted_text": "", "content_hash": "",
                "is_scraped": False, "error": "Source could not be safely retrieved",
            }

        soup = BeautifulSoup(html, "html.parser")

        # Remove scripts, styles, forms, ads
        for element in soup(["script", "style", "nav", "footer", "aside", "header", "form", "svg"]):
            element.decompose()

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text().strip()
        if not title:
            title = url

        # Extract Meta description / author
        authors = ""
        author_meta = soup.find("meta", attrs={"name": re.compile(r"author", re.I)}) or soup.find("meta", attrs={"property": re.compile(r"author", re.I)})
        if author_meta and author_meta.get("content"):
            authors = author_meta["content"].strip()

        date_meta = soup.find("meta", attrs={"property": "article:published_time"}) or soup.find("meta", attrs={"name": "date"})
        published_date = str(date_meta.get("content", "")).strip() if date_meta else ""

        # Extract paragraphs
        paragraphs = [p.get_text().strip() for p in soup.find_all("p") if len(p.get_text().strip()) > 30]
        extracted_text = "\n\n".join(paragraphs[:30])

        content_hash = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()

        return {
            "title": title,
            "authors": authors,
            "publisher": urlparse(target).hostname or "",
            "published_date": published_date,
            "extracted_text": extracted_text,
            "content_hash": content_hash,
            "is_scraped": True,
        }


web_scraper = WebScraper()
