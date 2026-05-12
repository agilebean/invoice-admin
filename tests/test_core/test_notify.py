"""Tests for invoice_admin.core.notify."""
from __future__ import annotations

from unittest.mock import patch

from invoice_admin.core.notify import Notification, Notifier


def test_notifier_send_success() -> None:
    n = Notifier(ntfy_topic="mytopic")
    note = Notification(title="t", body="b", priority="default", click_url=None)

    class Resp:
        status = 200

        def __enter__(self) -> Resp:
            return self

        def __exit__(self, *a: object) -> None:
            return None

    with patch("invoice_admin.core.notify.urllib.request.urlopen", return_value=Resp()):
        assert n.send(note) is True


def test_notifier_no_topic_returns_false() -> None:
    n = Notifier(ntfy_topic=None)
    note = Notification(title="t", body="b", priority="default", click_url=None)
    assert n.send(note) is False


def test_notifier_send_http_error_returns_false() -> None:
    import urllib.error

    n = Notifier(ntfy_topic="t")
    note = Notification(title="t", body="b", priority="default", click_url=None)

    def boom(*a: object, **k: object) -> None:
        raise urllib.error.HTTPError("url", 500, "err", hdrs=None, fp=None)

    with patch("invoice_admin.core.notify.urllib.request.urlopen", side_effect=boom):
        assert n.send(note) is False
