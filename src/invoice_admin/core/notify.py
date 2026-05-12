"""Push notifications via ntfy.sh (primary) and Pushover (optional)."""
from __future__ import annotations

import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    priority: str
    click_url: str | None


class Notifier:
    """Sends push notifications. Falls back gracefully."""

    def __init__(
        self,
        ntfy_topic: str | None = None,
        pushover_user: str | None = None,
        pushover_token: str | None = None,
    ) -> None:
        self._ntfy_topic = ntfy_topic
        self._pushover_user = pushover_user
        self._pushover_token = pushover_token

    def send(self, notification: Notification) -> bool:
        """Send to ntfy.sh. Returns True if 2xx, False otherwise. Never raises."""
        if not self._ntfy_topic:
            logger.warning("ntfy: no topic configured; skipping notification")
            return False
        url = f"https://ntfy.sh/{self._ntfy_topic}"
        headers: dict[str, str] = {
            "Title": notification.title,
            "Priority": notification.priority,
        }
        if notification.click_url:
            headers["Click"] = notification.click_url
        req = urllib.request.Request(
            url=url,
            data=notification.body.encode("utf-8"),
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw_code = getattr(resp, "status", None)
                if raw_code is None and hasattr(resp, "getcode"):
                    raw_code = resp.getcode()
                return 200 <= int(raw_code) < 300
        except urllib.error.HTTPError as e:
            logger.warning("ntfy HTTP error %s: %s", e.code, e.reason)
            return False
        except urllib.error.URLError as e:
            logger.warning("ntfy URL error: %s", e.reason)
            return False
        except OSError as e:
            logger.warning("ntfy I/O error: %s", e)
            return False
