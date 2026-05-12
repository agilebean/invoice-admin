"""Tests for invoice_admin.core.spark_link."""
from __future__ import annotations

from urllib.parse import unquote

import pytest

from invoice_admin.core.spark_link import (
    message_id_from_spark_open_url,
    spark_deep_link,
    spark_link_with_fallback,
)


def test_spark_deep_link_encodes_message_id() -> None:
    mid = "<abc+tag@mail.gmail.com>"
    url = spark_deep_link(mid)
    assert url.startswith("readdle-spark://openmessage?messageId=")
    encoded = url.split("messageId=", 1)[1]
    assert unquote(encoded) == mid


def test_message_id_from_spark_open_url_roundtrip() -> None:
    mid = "<abc+tag@mail.gmail.com>"
    url = spark_deep_link(mid)
    assert message_id_from_spark_open_url(url) == mid


def test_message_id_from_spark_open_url_invalid_scheme() -> None:
    with pytest.raises(ValueError, match="readdle-spark"):
        message_id_from_spark_open_url("https://example.com")
