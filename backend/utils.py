"""通用工具函数。"""
import random
import string
import time
from typing import Any, Dict


def rid(prefix: str) -> str:
    return f"{prefix}_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def now_ts() -> int:
    return int(time.time())


def err(code: str, message: str) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message}, "requestId": rid("req"), "ts": now_ts()}
