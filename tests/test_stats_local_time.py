from __future__ import annotations

import time

import pytest

from carbonio_bayes_trainer.stats import _format_local_timestamp


def test_formats_utc_timestamp_in_server_local_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        assert (
            _format_local_timestamp("2026-08-12T08:00:01.566252+00:00")
            == "2026-08-12 10:00:01 CEST"
        )
    finally:
        monkeypatch.delenv("TZ", raising=False)
        time.tzset()


def test_invalid_or_naive_timestamp_is_left_unchanged() -> None:
    assert _format_local_timestamp("not-a-timestamp") == "not-a-timestamp"
    assert _format_local_timestamp("2026-08-12T08:00:01") == "2026-08-12T08:00:01"
