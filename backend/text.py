"""Small string helpers: detecting Japanese script, cleaning up the model's
answers, and turning the final tags into a filename."""

import re

_JAPANESE = re.compile(r"[぀-ヿ一-鿿]")

# "opening"/"op"/"ending"/"ed"/"soundtrack"/"ost" as a standalone word, with an
# optional trailing number ("Opening 2", "ED3"). Word boundaries keep it from
# eating "Edward" or "Opposite".
_TYPE_LABEL = re.compile(r"\b(?:opening|op|ending|ed|soundtrack|ost)\b\.?\s*\d*", re.IGNORECASE)

_FILENAME_RESERVED = re.compile(r'[<>:"/\\|?*]')


def is_japanese(text):
    return bool(text) and bool(_JAPANESE.search(text))


def strip_type_labels(text):
    """Drop a stray "OP"/"ED 2"/"Opening" that the model left glued to a song or
    anime name, e.g. "Ending 2 | Alchemila" -> "Alchemila". The prompt tells it
    not to, but small models slip up."""
    if not text:
        return text
    cleaned = _TYPE_LABEL.sub(" ", text)
    cleaned = re.sub(r"[|｜]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" -|｜.")


def sanitize_filename(name):
    name = _FILENAME_RESERVED.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "untitled"


def build_display_title(anime, kind, number, song):
    """The name a track is saved under, e.g. "Frieren ED 2 - Anytime Anywhere"."""
    anime = (anime or "").strip()
    kind = (kind or "").strip()
    # The number is always a bare numeral, and OST doesn't take one.
    number = re.sub(r"\D", "", number or "")
    song = (song or "").strip()

    if kind.upper() == "OST":
        label = f"{anime} OST".strip()
    elif number:
        label = f"{anime} {kind} {number}".strip()
    else:
        label = f"{anime} {kind}".strip()
    label = re.sub(r"\s+", " ", label).strip()

    if not song:
        return label
    return f"{label} - {song}" if label else song
