"""Open a **Mail.app** outgoing message with subject, body, and PDF (macOS / AppleScript).

Step 2 of the monthly flow: same copy and attachment as SMTP ``send-test-pdf``, but the native MUA
draft so you can send from Mail (or duplicate the draft in Spark manually).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class MailAppDraftError(RuntimeError):
    """Mail.app / osascript invocation failed."""


def _applescript_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _applescript_string_expr(text: str) -> str:
    """AppleScript expression (quoted lines joined with ``return``) for UTF-8 text with newlines."""
    lines = text.split("\n")
    inner = " & return & ".join(f'"{_applescript_escape(line)}"' for line in lines)
    return inner
def _pdf_path_for_attachment(
    pdf_path: Path, attachment_name: str
) -> tuple[Path, Path | None]:
    """Return ``(absolute_path_for_attachment, temp_dir_or_none)``.

    When ``attachment_name`` matches the PDF basename, no copy. Otherwise copy into a temp directory
    (entire directory removed after ``osascript``).
    """
    pdf_path = pdf_path.expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(str(pdf_path))
    if attachment_name == pdf_path.name:
        return pdf_path, None
    tmpdir = Path(tempfile.mkdtemp(prefix="googleads-mail-draft-"))
    dest = tmpdir / attachment_name
    shutil.copy2(pdf_path, dest)
    return dest, tmpdir


def build_open_draft_applescript(
    *,
    to_address: str,
    subject: str,
    body: str,
    pdf_path: Path,
) -> str:
    """Return an AppleScript source string (UTF-8) to create a visible draft with attachment."""
    to_address = to_address.strip()
    pdf_path = pdf_path.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(str(pdf_path))

    subj = _applescript_escape(subject)
    body_expr = _applescript_string_expr(body)
    to_esc = _applescript_escape(to_address)
    posix = str(pdf_path).replace("\\", "\\\\")

    return f'''tell application "Mail"
  set msg to make new outgoing message with properties {{visible:true, subject:"{subj}"}}
  tell msg
    make new to recipient at end of to recipients with properties {{address:"{to_esc}"}}
    set content to {body_expr}
    make new attachment with properties {{file name:(POSIX file "{posix}")}} at after the last paragraph
  end tell
  activate
end tell
'''


def open_mail_app_draft(
    *,
    to_address: str,
    subject: str,
    body: str,
    pdf_path: Path,
    attachment_name: str,
) -> None:
    """Tell Mail.app to open a new outgoing message with the given PDF attached."""
    if sys.platform != "darwin":
        raise MailAppDraftError(
            "mail-app-draft only runs on macOS (Mail.app + osascript)."
        )
    path_for_mail, tmpdir = _pdf_path_for_attachment(pdf_path, attachment_name)
    try:
        script = build_open_draft_applescript(
            to_address=to_address,
            subject=subject,
            body=body,
            pdf_path=path_for_mail,
        )
        proc = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise MailAppDraftError(
                f"osascript exited {proc.returncode}" + (f": {err}" if err else "")
            )
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)
