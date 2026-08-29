import re

CORNER_QUOTE_RE = re.compile(r"[『「]([^』」]+)[』」]")
# "TVアニメ「Anime Name」..." / "アニメ『Anime Name』..." - a very common
# convention where the bracket holds the ANIME name, not a song title.
ANIME_BRACKET_RE = re.compile(r"(?:tv)?\s*(?:ｱﾆﾒ|アニメ|anime)\s*[『「]([^』」]+)[』」]", re.IGNORECASE)
BY_ARTIST_RE = re.compile(r"\bby\s+([^([|｜\-–—]+)", re.IGNORECASE)

TYPE_WORDS = {
    "opening": "OP",
    "op": "OP",
    "ending": "ED",
    "ed": "ED",
    "soundtrack": "OST",
    "ost": "OST",
}
TYPE_ALT = "|".join(TYPE_WORDS.keys())
PREFIX_TYPE_RE = re.compile(rf"^({TYPE_ALT})\.?\s*(\d+)?\s+(.+)$", re.IGNORECASE)
SUFFIX_TYPE_RE = re.compile(rf"^(.+?)\s+({TYPE_ALT})\.?\s*(\d+)?$", re.IGNORECASE)
BARE_TYPE_RE = re.compile(rf"({TYPE_ALT})", re.IGNORECASE)


def _find_type_anywhere(text):
    """Looser than _extract_anime_type: just spot an OP/ED/OST word and a
    nearby number anywhere in a text fragment, with no anime name expected
    (used for the leftover text after an "アニメ「Name」" match, e.g.
    "ノンクレジットOP映像")."""
    m = BARE_TYPE_RE.search(text)
    if not m:
        return None
    number_m = re.search(r"\d+", text)
    return {"type": TYPE_WORDS[m.group(1).lower()], "number": number_m.group(0) if number_m else ""}


def _extract_anime_type(title):
    """Detects "{Anime} - Opening 1" / "OP 2 {Anime}" style titles - very
    common for anime clips. This must run before the generic "Artist - Song"
    fallback below, otherwise a title like "Kami Nomi zo Shiru Sekai -
    Opening 1" gets misread as artist="Kami Nomi zo Shiru Sekai",
    song="Opening 1" (a type/number label, not a song title at all)."""
    cleaned = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", title).strip(" |｜-–—")

    m = PREFIX_TYPE_RE.match(cleaned)
    if m:
        return {"anime": m.group(3).strip(" -|｜"), "type": TYPE_WORDS[m.group(1).lower()], "number": m.group(2) or ""}
    m = SUFFIX_TYPE_RE.match(cleaned)
    if m:
        return {"anime": m.group(1).strip(" -|｜"), "type": TYPE_WORDS[m.group(2).lower()], "number": m.group(3) or ""}
    return None


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "untitled"


def guess_fields_from_title(title):
    type_guess = _extract_anime_type(title)
    anime_bracket_match = ANIME_BRACKET_RE.search(title)

    song = ""
    artist = ""

    # Only read a generic corner-bracket as a SONG title if it isn't
    # actually the "アニメ「Anime Name」" convention above.
    if not anime_bracket_match:
        bracket_match = CORNER_QUOTE_RE.search(title)
        if bracket_match:
            song = bracket_match.group(1).strip()

    by_match = BY_ARTIST_RE.search(title)
    if by_match:
        artist = by_match.group(1).strip()

    if song or artist:
        result = {"artist": artist, "song": song}
        if type_guess:
            result.update(type_guess)
        elif anime_bracket_match:
            result["anime"] = anime_bracket_match.group(1).strip()
        return result

    if type_guess:
        # The title only states "{Anime} - {Type} {Number}" - the song/artist
        # aren't in there at all, so leave them empty for AI/description
        # escalation instead of misreading the type label as a song title.
        return {**type_guess, "artist": "", "song": ""}

    if anime_bracket_match:
        # We have the anime name but not yet its type/number from this
        # pattern alone - check the text right after the bracket for one
        # (e.g. "アニメ「X」ノンクレジットOP映像").
        remainder_guess = _find_type_anywhere(title[anime_bracket_match.end():]) or {"type": "OP", "number": ""}
        return {
            "anime": anime_bracket_match.group(1).strip(),
            "artist": "",
            "song": "",
            **remainder_guess,
        }

    # Fallback for plain "Artist - Song" style titles.
    cleaned = re.sub(r"\[[^\]]*\]|\([^)]*\)|[『「][^』」]*[』」]", "", title).strip()
    if " - " in cleaned:
        left, right = cleaned.split(" - ", 1)
        return {"artist": left.strip(), "song": right.strip()}

    # No reliable pattern found - leave both empty rather than dumping the
    # raw title (with separators like "|" still in it) into "song". An
    # honest "unknown" lets AI/description/web-search fill it in properly,
    # instead of a bad guess blocking them because it isn't empty.
    return {"artist": "", "song": ""}


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
