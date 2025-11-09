"""Notification helpers for the memorial application."""
from __future__ import annotations

import logging
from typing import Optional

import requests
from flask import current_app

LOGGER = logging.getLogger(__name__)
_DEFAULT_TOPIC = "https://ntfy.sh/JAYDEVSUBUDHINOTIFICATIONS"


def notify_new_tribute(
    *,
    tribute_id: int,
    tribute_name: str,
    tribute_message: str,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Send an ntfy notification about a newly created tribute."""
    log = logger or LOGGER
    topic = current_app.config.get("NTFY_TOPIC", _DEFAULT_TOPIC)
    summary = f"New tribute from {tribute_name}" if tribute_name else "New tribute"
    body_lines = [summary, f"ID: {tribute_id}"]
    if tribute_message:
        snippet = tribute_message.strip().splitlines()[0][:160]
        body_lines.append(snippet)
    payload = "\n".join(body_lines)

    try:
        requests.post(
            topic,
            data=payload.encode("utf-8"),
            headers={"Title": summary},
            timeout=5,
        )
    except requests.RequestException as exc:  # pragma: no cover - network errors
        log.warning("Notification dispatch failed: %s", exc)
