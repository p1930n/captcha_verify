from __future__ import annotations

OK_EMOJI_ID = "128076"
OK_EMOJI_SYMBOL = "👌"
QUESTION_EMOJI_ID = "10068"
QUESTION_EMOJI_LEGACY_ID = "10067"
QUESTION_EMOJI_SYMBOL = "❓"


def accepted_ok_emoji_ids(ok_emoji_id: str) -> frozenset[str]:
    if ok_emoji_id == OK_EMOJI_ID:
        return frozenset((OK_EMOJI_ID, OK_EMOJI_SYMBOL))
    return frozenset((ok_emoji_id,))


def accepted_question_emoji_ids(question_emoji_id: str) -> frozenset[str]:
    if question_emoji_id == QUESTION_EMOJI_ID:
        return frozenset((QUESTION_EMOJI_ID, QUESTION_EMOJI_LEGACY_ID, QUESTION_EMOJI_SYMBOL))
    return frozenset((question_emoji_id,))
