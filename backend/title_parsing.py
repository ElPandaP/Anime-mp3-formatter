import re

TYPE_WORDS = {
    "opening": "OP",
    "op": "OP",
    "ending": "ED",
    "ed": "ED",
    "soundtrack": "OST",
    "ost": "OST",
}
TYPE_ALT = "|".join(TYPE_WORDS.keys())
# A standalone OP/ED/OST(+number) token anywhere in a string, word-boundaried
# so "Edward" or "Opposite" are never touched - only an exact "op"/"ed"/
# "opening"/"ending"/"ost"/"soundtrack" word counts.
TYPE_LABEL_TOKEN_RE = re.compile(rf"\b(?:{TYPE_ALT})\b\.?\s*\d*", re.IGNORECASE)


def strip_type_labels(text):
    """Remove a stray OP/ED/OST(+number) label stuck onto a song or anime
    name (e.g. "Ending 2 | Alchemila" -> "Alchemila"). The AI is told not to
    include these, but sometimes echoes one back as if it were the real
    name - this is the last-line cleanup for that."""
    if not text:
        return text
    cleaned = TYPE_LABEL_TOKEN_RE.sub(" ", text)
    cleaned = re.sub(r"[|｜]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" -|｜.")


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "untitled"


def build_display_title(anime, kind, number, song):
    anime = (anime or "").strip()
    kind = (kind or "").strip()
    number = (number or "").strip()
    song = (song or "").strip()

    if kind.upper() == "OST":
        label = f"{anime} OST".strip()
    elif number:
        label = f"{anime} {kind} {number}".strip()
    else:
        label = f"{anime} {kind}".strip()

    label = re.sub(r"\s+", " ", label).strip()
    if song:
        return f"{label} - {song}" if label else song
    return label
