from __future__ import annotations

import io
import re
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .spamassassin import SpamAssassinTrainer

_FOLDER_ROW = re.compile(r"^\s*(\d+)\s+\S+\s+\d+\s+\d+\s+(/.*)\s*$")


@dataclass(frozen=True)
class MailFolder:
    folder_id: int
    path: str


@dataclass(frozen=True)
class BootstrapResult:
    folders: int
    exported: int
    learned: int
    failed: int
    duration_seconds: float


class HamBootstrapper:
    """Import administrator-selected Carbonio folders as known Ham."""

    def __init__(
        self,
        *,
        zmmailbox_path: str,
        trainer: SpamAssassinTrainer,
        batch_size: int = 50,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self.zmmailbox_path = zmmailbox_path
        self.trainer = trainer
        self.batch_size = batch_size

    def list_folders(self, account: str) -> tuple[MailFolder, ...]:
        result = subprocess.run(
            [self.zmmailbox_path, "-z", "-m", account, "getAllFolders"],
            check=False,
            capture_output=True,
            text=True,
        )
        self._require_success(result, f"folder listing for {account}")

        folders: list[MailFolder] = []
        for line in result.stdout.splitlines():
            match = _FOLDER_ROW.match(line)
            if match:
                folders.append(MailFolder(int(match.group(1)), match.group(2).rstrip()))
        return tuple(folders)

    def select_folders(
        self,
        account: str,
        folder_path: str,
        *,
        recursive: bool,
    ) -> tuple[MailFolder, ...]:
        normalized = folder_path.rstrip("/") or "/"
        folders = self.list_folders(account)
        selected = tuple(
            folder
            for folder in folders
            if folder.path == normalized
            or (recursive and folder.path.startswith(normalized.rstrip("/") + "/"))
        )
        if not selected:
            raise ValueError(f"Folder not found: {folder_path}")
        return selected

    def run(
        self,
        *,
        account: str,
        folder_path: str,
        recursive: bool = False,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> BootstrapResult:
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")

        started = time.monotonic()
        folders = self.select_folders(account, folder_path, recursive=recursive)
        exported = 0
        learned = 0
        failed = 0

        with tempfile.TemporaryDirectory(prefix="carbonio-bootstrap-ham-") as temp_dir:
            temp_path = Path(temp_dir)
            pending: list[Path] = []

            for folder in folders:
                archive = self._export_folder(account, folder.folder_id)
                if archive is None:
                    continue
                with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                    for member in tar:
                        if not member.isfile() or not member.name.lower().endswith(".eml"):
                            continue
                        if limit is not None and exported >= limit:
                            break
                        source = tar.extractfile(member)
                        if source is None:
                            continue
                        exported += 1
                        message_path = temp_path / f"{exported:08d}.eml"
                        message_path.write_bytes(source.read())
                        pending.append(message_path)

                        if not dry_run and len(pending) >= self.batch_size:
                            ok, _ = self.trainer.train_batch(tuple(pending), "ham")
                            if ok:
                                learned += len(pending)
                            else:
                                failed += len(pending)
                            for path in pending:
                                path.unlink(missing_ok=True)
                            pending.clear()

                if limit is not None and exported >= limit:
                    break

            if not dry_run and pending:
                ok, _ = self.trainer.train_batch(tuple(pending), "ham")
                if ok:
                    learned += len(pending)
                else:
                    failed += len(pending)

        return BootstrapResult(
            folders=len(folders),
            exported=exported,
            learned=learned,
            failed=failed,
            duration_seconds=time.monotonic() - started,
        )

    def _export_folder(self, account: str, folder_id: int) -> bytes | None:
        result = subprocess.run(
            [
                self.zmmailbox_path,
                "-z",
                "-m",
                account,
                "-t",
                "0",
                "getRestURL",
                f"//?fmt=tgz&query=inid:{folder_id}",
            ],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            details = result.stderr.decode(errors="replace").strip() or "no command output"
            normalized = details.lower()
            if "status=204" in normalized or "no content" in normalized:
                return None
            raise RuntimeError(f"Carbonio folder export failed: {details}")
        if not result.stdout:
            return None
        return result.stdout

    @staticmethod
    def _require_success(result: subprocess.CompletedProcess[str], operation: str) -> None:
        if result.returncode == 0:
            return
        details = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise RuntimeError(f"Carbonio {operation} failed: {details}")
