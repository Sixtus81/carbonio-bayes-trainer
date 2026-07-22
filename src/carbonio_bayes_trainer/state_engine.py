from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .database import MessageState

TrainingAction = Literal["spam", "ham"]


@dataclass(frozen=True)
class TransitionDecision:
    action: TrainingAction | None
    reason: str


def decide_transition(
    previous: MessageState | None,
    current_folder: str,
    inbox_folder: str,
    junk_folder: str,
) -> TransitionDecision:
    """Decide whether a folder state change should trigger Bayes training."""

    if current_folder == junk_folder:
        if previous is None:
            return TransitionDecision("spam", "message first observed in junk")
        if previous.folder != junk_folder or previous.trained_as != "spam":
            return TransitionDecision("spam", "message moved to junk")
        return TransitionDecision(None, "message already trained as spam")

    if current_folder == inbox_folder:
        if previous is None:
            return TransitionDecision(None, "new inbox message is not implicit ham")
        if previous.folder == junk_folder and previous.trained_as == "spam":
            return TransitionDecision("ham", "previously trained spam moved to inbox")
        return TransitionDecision(None, "no relevant inbox transition")

    return TransitionDecision(None, "folder is not configured for training")
