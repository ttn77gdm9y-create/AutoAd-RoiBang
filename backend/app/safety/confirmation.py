from __future__ import annotations

from fastapi import HTTPException

EXECUTE_CONFIRMATION_PHRASE = "确认执行"
CONFIRMATION_REQUIRED_MESSAGE = f"真实执行前必须输入：{EXECUTE_CONFIRMATION_PHRASE}"


def require_execute_confirmation(value: str) -> None:
    if value != EXECUTE_CONFIRMATION_PHRASE:
        raise HTTPException(status_code=400, detail=CONFIRMATION_REQUIRED_MESSAGE)

