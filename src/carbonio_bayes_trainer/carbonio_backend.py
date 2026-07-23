from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from email import policy
from email.parser import BytesHeaderParser
from pathlib import Path

from .backend import MailboxMessage

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

# Carbonio 26.x prefixes search results with a row number, for example:
# "1. 156438  mess ...". Older Zimbra/Carbonio versions may emit only the
# message ID. Support both formats and capture the actual mailbox message ID.
_MESSAGE_ROW = re.compile(r"^\s*(?:\d+\.\s+)?(\d+)\s+mess\b")


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


class CarbonioBackend:
    """Mailbox backend using Carbonio's supported command-line tools."""

    def __init__(
        self,
        *,
        zmmailbox_path: str = "/opt/zextras/bin/zmmailbox",
        carbonio_path: str = "/opt/zextras/bin/carbonio",
        rest_url: str = "http://127.0.0.1:8080",
        max_messages_per_folder: int = 1000,
        runner: CommandRunner = _run,
    ) -> None:
        if not 1 <= max_messages_per_folder <= 1000:
            raise ValueError("max_messages_per_folder must be between 1 and 1000")
        self.zmmailbox_path = zmmailbox_path
        self.carbonio_path = carbonio_path
        self.rest_url = rest_url.rstrip("/")
        self.max_messages_per_folder = max_messages_per_folder
        self.runner = runner

    def list_accounts(self) -> Sequence[str]:
        result = self.runner([self.carbonio_path, "prov", "-l", "gaa"])
        self._require_success(result, "account discovery")
        return tuple(
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and "@" in line
        )

    def list_messages(self, account: str, folder: str) -> Sequence[MailboxMessage]:
        result = self.runner(
            [
                self.zmmailbox_path,
                "-z",
                "-m",
                account,
                "s",
                "-t",
                "message",
                "-l",
                str(self.max_messages_per_folder),
                f"in:{folder}",
            ]
        )
        self._require_success(result, f"message listing for {account}:{folder}")

        messages: list[MailboxMessage] = []
        for line in result.stdout.splitlines():
            match = _MESSAGE_ROW.match(line)
            if match is None:
                continue
            messages.append(
                MailboxMessage(
                    account=account,
                    message_key=match.group(1),
                    folder=folder,
                )
            )
        return tuple(messages)

    def export_message(self, message: MailboxMessage, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)

        result = self.runner(
            [
                self.zmmailbox_path,
                "-z",
                "-m",
                message.account,
                "-t",
                "0",
                "gru",
                "-u",
                self.rest_url,
                "-o",
                str(destination),
                f"//?id={message.message_key}",
            ]
        )
        self._require_success(result, f"RFC822 export for {message.account}:{message.message_key}")
        self._validate_rfc822(destination)

    def stable_message_key(self, message: MailboxMessage) -> str:
        with tempfile.TemporaryDirectory(prefix="carbonio-identity-") as temp_dir:
            path = Path(temp_dir) / f"{message.message_key}.eml"
            self.export_message(message, path)
            return self._stable_key_from_rfc822(path)

    @staticmethod
    def _stable_key_from_rfc822(path: Path) -> str:
        raw = path.read_bytes()
        parsed = BytesHeaderParser(policy=policy.default).parsebytes(raw)
        message_id = str(parsed.get("Message-ID", "")).strip()
        if message_id:
            return f"message-id:{message_id.lower()}"
        return f"sha256:{hashlib.sha256(raw).hexdigest()}"

    @staticmethod
    def _require_success(result: subprocess.CompletedProcess[str], operation: str) -> None:
        if result.returncode == 0:
            return
        details = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise RuntimeError(f"Carbonio {operation} failed: {details}")

    @staticmethod
    def _validate_rfc822(path: Path) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("Carbonio export produced an empty RFC822 file")

        with path.open("rb") as handle:
            header_block = handle.read(256 * 1024).split(b"\r\n\r\n", 1)[0]

        normalized = header_block.lower()
        required = (b"message-id:", b"received:")
        if not all(header in normalized for header in required):
            raise RuntimeError("Carbonio export is missing required RFC822 headers")
        if b"mime-version:" not in normalized and b"content-type:" not in normalized:
            raise RuntimeError("Carbonio export is missing MIME metadata")
