import re

ROMANIZATION_RULE = (
    "Prefer the romanized/English name for song and artist (e.g. \"Tabibito no "
    "Uta\", not \"旅人の唄\"). Only use Japanese script if no romanized version "
    "exists anywhere."
)

JAPANESE_SCRIPT_RE = re.compile(r"[぀-ヿ一-鿿]")


def is_japanese(text):
    return bool(text) and bool(JAPANESE_SCRIPT_RE.search(text))


def strip_japanese(text):
    """Never surface raw kanji/kana here - treat it the same as "unknown" so
    later steps (which can actually search for a romanized version) get a
    chance to run, instead of a guessed transliteration that might be wrong."""
    return "" if is_japanese(text) else text
