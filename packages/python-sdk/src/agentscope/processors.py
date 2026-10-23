import re
from collections.abc import Callable
from copy import deepcopy
from typing import Any, cast

type EventProcessor = Callable[[dict[str, Any]], dict[str, Any]]

EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")
API_KEY_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|as_(?:live|test)_[A-Za-z0-9_-]+)\b")
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*\b")


def _processor(pattern: re.Pattern[str], replacement: str) -> EventProcessor:
    def process(event: dict[str, Any]) -> dict[str, Any]:
        changed = False

        def visit(value: Any) -> Any:
            nonlocal changed
            if isinstance(value, str):
                redacted, count = pattern.subn(replacement, value)
                changed = changed or count > 0
                return redacted
            if isinstance(value, list):
                return [visit(item) for item in value]
            if isinstance(value, dict):
                return {key: visit(item) for key, item in value.items()}
            return value

        output = visit(deepcopy(event))
        if changed:
            payload = output.setdefault("payload", {})
            metadata = payload.setdefault("metadata", {})
            metadata["agentscope.redacted"] = True
        return cast(dict[str, Any], output)

    return process


def redact_emails() -> EventProcessor:
    return _processor(EMAIL_PATTERN, "[REDACTED_EMAIL]")


def redact_credit_cards() -> EventProcessor:
    return _processor(CARD_PATTERN, "[REDACTED_CARD]")


def redact_api_keys() -> EventProcessor:
    return _processor(API_KEY_PATTERN, "[REDACTED_API_KEY]")


def redact_bearer_tokens() -> EventProcessor:
    return _processor(BEARER_PATTERN, "Bearer [REDACTED_TOKEN]")


def default_redaction() -> list[EventProcessor]:
    return [redact_emails(), redact_credit_cards(), redact_api_keys(), redact_bearer_tokens()]
