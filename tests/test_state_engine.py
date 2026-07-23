from carbonio_bayes_trainer.database import MessageState
from carbonio_bayes_trainer.state_engine import decide_transition


def state(folder: str, trained_as: str | None) -> MessageState:
    return MessageState(
        account="user@example.com",
        message_key="message-1",
        stable_key="<stable@example.com>",
        folder=folder,
        trained_as=trained_as,
        updated_at="2026-07-22T00:00:00+00:00",
    )


def test_first_seen_in_junk_is_spam() -> None:
    decision = decide_transition(None, "/Junk", "/Inbox", "/Junk")
    assert decision.action == "spam"


def test_first_seen_in_inbox_is_not_ham() -> None:
    decision = decide_transition(None, "/Inbox", "/Inbox", "/Junk")
    assert decision.action is None


def test_move_from_inbox_to_junk_is_spam() -> None:
    previous = state("/Inbox", None)
    decision = decide_transition(previous, "/Junk", "/Inbox", "/Junk")
    assert decision.action == "spam"


def test_spam_remaining_in_junk_is_not_retrained() -> None:
    previous = state("/Junk", "spam")
    decision = decide_transition(previous, "/Junk", "/Inbox", "/Junk")
    assert decision.action is None


def test_spam_moved_back_to_inbox_is_ham() -> None:
    previous = state("/Junk", "spam")
    decision = decide_transition(previous, "/Inbox", "/Inbox", "/Junk")
    assert decision.action == "ham"


def test_unknown_folder_does_not_train() -> None:
    decision = decide_transition(None, "/Archive", "/Inbox", "/Junk")
    assert decision.action is None
