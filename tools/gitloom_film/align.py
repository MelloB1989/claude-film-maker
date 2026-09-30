"""Character-level TTS alignment → word timings.

A word's time is the span of its letters and digits; punctuation rides along in the display text. A token of
punctuation only (a detached "...") joins the word before it.
"""
from dataclasses import dataclass


@dataclass
class Word:
    w: str
    start: float
    end: float


def words_from_alignment(al: dict) -> list[Word]:
    chars = al["characters"]
    st = al["character_start_times_seconds"]
    en = al["character_end_times_seconds"]
    if not (len(chars) == len(st) == len(en)):
        raise ValueError("alignment arrays differ in length")
    words: list[Word] = []
    cur: list[int] = []

    def flush() -> None:
        if not cur:
            return
        token = "".join(chars[i] for i in cur)
        core = [i for i in cur if chars[i].isalnum()]
        if core:
            words.append(Word(token, float(st[core[0]]), float(en[core[-1]])))
        elif words:
            words[-1].w += token
        cur.clear()

    for i, ch in enumerate(chars):
        if ch.isspace():
            flush()
        else:
            cur.append(i)
    flush()
    return words


def words_to_dicts(words: list[Word]) -> list[dict]:
    return [{"w": w.w, "start": round(w.start, 4), "end": round(w.end, 4)} for w in words]
