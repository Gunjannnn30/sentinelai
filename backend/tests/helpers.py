"""Small builders shared across the test suite."""

from typing import Any


def chat_body(content: str = "Say hello", **overrides: Any) -> dict[str, Any]:
    """A valid chat completion payload; ``overrides`` win over defaults."""
    body: dict[str, Any] = {
        "model": "sentinel-mock-small",
        "messages": [{"role": "user", "content": content}],
    }
    body.update(overrides)
    return body
