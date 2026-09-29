from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app import logging_config
from app.main import app

CID_PATTERN = re.compile(r"^req-[0-9a-f]{8}$")


def _post_chat(headers: dict[str, str] | None = None, message: str = "Explain observability"):
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                headers=headers or {},
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": message,
                },
            )

    return asyncio.run(send())


def test_generates_correlation_id_and_response_headers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    response = _post_chat()

    cid = response.headers["x-request-id"]
    assert CID_PATTERN.match(cid)
    assert response.json()["correlation_id"] == cid
    assert float(response.headers["x-response-time-ms"]) >= 0


def test_reuses_valid_incoming_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    response = _post_chat(headers={"x-request-id": "req-abcdef12"})
    assert response.headers["x-request-id"] == "req-abcdef12"


def test_rejects_malformed_incoming_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    response = _post_chat(headers={"x-request-id": "not-a-valid-id"})
    assert CID_PATTERN.match(response.headers["x-request-id"])


def test_api_logs_are_enriched_and_scrubbed(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    response = _post_chat(message="Call 0901234567 or mail a@b.com, card 4111 1111 1111 1111")

    raw = log_path.read_text(encoding="utf-8")
    assert "0901234567" not in raw
    assert "a@b.com" not in raw
    assert "4111 1111 1111 1111" not in raw

    api_events = [e for e in map(json.loads, raw.splitlines()) if e.get("service") == "api"]
    assert api_events
    for event in api_events:
        assert event["correlation_id"] == response.headers["x-request-id"]
        for field in ("user_id_hash", "session_id", "feature", "model", "env"):
            assert field in event
        assert event["user_id_hash"] != "student-01"
