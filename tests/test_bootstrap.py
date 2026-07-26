from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path

from carbonio_bayes_trainer.bootstrap import HamBootstrapper


class FakeTrainer:
    def __init__(self) -> None:
        self.batches: list[tuple[Path, ...]] = []

    def train_batch(self, paths: tuple[Path, ...], action: str) -> tuple[bool, str]:
        assert action == "ham"
        assert all(path.is_file() for path in paths)
        self.batches.append(paths)
        return True, "learned"


def _tgz_with_duplicate_names(count: int) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for number in range(count):
            content = (
                f"From: sender{number}@example.test\n"
                f"Subject: Message {number}\n"
                "\n"
                "Body\n"
            ).encode()
            info = tarfile.TarInfo("message.eml")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def test_recursive_folder_selection(monkeypatch) -> None:
    listing = """
 55777 mess 372 0 /Inbox/04_Arbeit/AKOM
 55778 mess 10 0 /Inbox/04_Arbeit/AKOM/Archive
 55779 mess 3 0 /Inbox/Other
"""

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout=listing, stderr="")

    monkeypatch.setattr("carbonio_bayes_trainer.bootstrap.subprocess.run", fake_run)
    bootstrapper = HamBootstrapper(
        zmmailbox_path="zmmailbox",
        trainer=FakeTrainer(),  # type: ignore[arg-type]
    )

    selected = bootstrapper.select_folders(
        "user@example.test", "/Inbox/04_Arbeit/AKOM", recursive=True
    )

    assert [folder.folder_id for folder in selected] == [55777, 55778]


def test_duplicate_archive_names_are_all_learned(monkeypatch) -> None:
    trainer = FakeTrainer()
    bootstrapper = HamBootstrapper(
        zmmailbox_path="zmmailbox",
        trainer=trainer,  # type: ignore[arg-type]
        batch_size=2,
    )
    monkeypatch.setattr(
        bootstrapper,
        "select_folders",
        lambda account, folder_path, recursive: (
            type("Folder", (), {"folder_id": 55777, "path": folder_path})(),
        ),
    )

    def fake_export(account: str, folder_id: int) -> bytes:
        return _tgz_with_duplicate_names(5)

    monkeypatch.setattr(
        bootstrapper,
        "_export_folder",
        fake_export,
    )

    result = bootstrapper.run(
        account="user@example.test",
        folder_path="/Inbox/Ham",
    )

    assert result.exported == 5
    assert result.learned == 5
    assert result.failed == 0
    assert [len(batch) for batch in trainer.batches] == [2, 2, 1]
