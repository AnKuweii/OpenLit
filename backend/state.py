"""进程内共享状态"""
from typing import Any, Dict

current_pdf: Dict[str, Any] = {
    "fileId": None,
    "name": None,
    "pages": 0,
    "status": "idle",  # idle | parsing | ready | error
    "progress": 0,
}

# citationId -> { fileId, page, snippet, bbox, previewUrl }
citations: Dict[str, Dict[str, Any]] = {}
