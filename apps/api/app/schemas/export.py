from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, ConfigDict


class ExportRequest(BaseModel):
    report_id: str
    export_format: str = Field(default="docx")  # docx, pdf, html, md
    review_draft: bool = False
    include_cover: bool = True
    include_toc: bool = True
    include_references: bool = True
    include_page_numbers: bool = True
    citation_style: str = "IEEE"
    template_version_id: Optional[str] = None


class ExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    report_id: str
    export_format: str
    download_url: str
    filename: str
    file_size: int
    created_at: datetime
