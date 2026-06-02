import pytest
from fastapi import HTTPException

from backend.app.safety.confirmation import CONFIRMATION_REQUIRED_MESSAGE
from backend.app.safety.confirmation import EXECUTE_CONFIRMATION_PHRASE
from backend.app.safety.confirmation import require_execute_confirmation


def test_require_execute_confirmation_accepts_exact_phrase():
    require_execute_confirmation(EXECUTE_CONFIRMATION_PHRASE)


def test_require_execute_confirmation_rejects_other_text():
    with pytest.raises(HTTPException) as exc_info:
        require_execute_confirmation("我已确认")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == CONFIRMATION_REQUIRED_MESSAGE
