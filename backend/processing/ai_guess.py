"""Work out anime / type / number / song / artist for a video.

Everything comes from one LLM call over the title and description - no regex
parsing of titles, they're too inconsistent for that. What's layered on top is
a recovery pass: when the model returns a field empty or still in kanji, look
the name up in a real database (AniList for the anime, the iTunes catalogue for
the song) where the official romanization already exists.
"""

import re

from errors import RateLimitedError, VideoUnavailableError
from sources.catalog import search_anime_cover, search_artwork
from sources.llm_client import call_llm, extract_json
from sources.youtube import get_video_description
from text import is_japanese, strip_type_labels

# Fields the recovery pass can look up online (type/number always come from the
# LLM). anime -> AniList, song/artist -> iTunes.
FIELDS = ("anime", "song", "artist")

ROMANIZATION_RULE = (
    'Prefer the romanized/English name for song and artist ("Tabibito no Uta", '
    'not "旅人の唄"). Only fall back to Japanese script if nothing romanized exists.'
)

# Things a small model sometimes hands back as if they were a song name when the
# title didn't actually name one: a "Full"/"[4K]" tag, or the type label itself
# ("Opening 1", "ED FULL").
JUNK_VALUE_RE = re.compile(
    r"^(op|opening|ed|ending|ost|soundtrack|nc\s*op|nc\s*ed|ncop|nced|creditless|"
    r"full|short|hd|4k|8k|uhd|tv\s*size|movie|trailer|pv|mv|amv|lyrics|official|"
    r"video|audio|\d+\s*fps)\.?\s*\d*$",
    re.IGNORECASE,
)


def _is_junk(value):
    return bool(value) and bool(JUNK_VALUE_RE.match(value.strip()))


def _all_resolved(guess):
    return all(guess.get(key) for key in FIELDS)


def ai_extract_metadata(title, description, hint=None):
    """Primary extraction: title + description -> all five fields, one call."""
    hint_line = ""
    if hint:
        parts = [f"{k}={hint[k]}" for k in ("anime", "type", "number") if hint.get(k)]
        if parts:
            hint_line = (
                "The user was searching for: " + ", ".join(parts) + ". Use this as a "
                "strong hint, but correct it if the title or description clearly says "
                "otherwise.\n"
            )

    prompt = (
        "You extract anime song metadata from a YouTube video's title and description.\n"
        "- anime: the show's name only. Keep a season marker that's part of the name "
        "(\"Season 2\", \"S4\"); drop \"NCOP\", \"Creditless\", episode numbers.\n"
        "- type: OP, ED or OST.\n"
        "- number: the numeral attached to the type - \"Opening 2\", \"ED 3\", \"OP2\" "
        "all give \"2\"/\"3\"/\"2\". No numeral shown (or only words like Full, TV, "
        "NCOP) -> \"\".\n"
        "- song: the clean song title - no quote marks or brackets (『』「」\"\"''), no "
        "\"Full\"/\"TV size\"/\"Lyrics\"/\"Creditless\".\n"
        "- artist: the performing artist or band, if named in the title or the description.\n"
        "Official channels (Crunchyroll, Aniplex, label channels) often list \"Anime:\", "
        "\"Song:\", \"Artist:\" explicitly in the description - trust those over the title.\n"
        f"{ROMANIZATION_RULE}\n"
        "Use \"\" for any field the title and description do not clearly state. Never "
        "invent a plausible-sounding name, and never put a type label (\"Opening\", "
        "\"OP\", a bare number) in the song or artist field.\n"
        f"{hint_line}"
        f"\nTitle: {title}\n"
        f"Description:\n{(description or '(none)')[:2000]}\n\n"
        'Reply with ONLY JSON, no prose: '
        '{"anime": "", "type": "OP", "number": "", "song": "", "artist": ""}'
    )

    try:
        parsed = extract_json(call_llm(prompt))
    except Exception:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def itunes_song_snippets(query, max_results=200):
    """iTunes's catalog as a stand-in for a web search: no API key, no
    bot-detection wall, and it already stores properly romanized official
    artist/track names - plus the anime name itself often shows up in the
    collection/album title (e.g. "Song (From "Attack on Titan")")."""
    try:
        candidates = search_artwork(query, limit=max_results)
    except Exception:
        return []
    return [
        f"{c['artist']} - {c['track']} ({c.get('collection', '')})"
        for c in candidates
        if c.get("track")
    ]


def _mentions_anime(anime, snippet):
    """Loose keyword check: does this iTunes snippet plausibly refer to the
    anime we already know? iTunes's fuzzy search can return a single,
    unrelated "closest match" for an obscure/romanized query - the LLM tends
    to accept whatever it's given, so filter those out first. Handles a
    still-Japanese anime name too (iTunes snippets often embed the native
    title verbatim)."""
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", anime) if len(w) > 2]
    if words:
        snippet_lower = snippet.lower()
        if any(w in snippet_lower for w in words):
            return True
    japanese_runs = re.findall(r"[぀-ヿ一-鿿]{2,}", anime)
    if japanese_runs:
        if any(run in snippet for run in japanese_runs):
            return True
    if not words and not japanese_runs:
        return True  # nothing meaningful to check against - don't block
    return False


def ai_romanize_from_itunes(title, guess, snippets):
    """Fill fields that are still empty using the iTunes catalog matches -
    only ever fills gaps, never overrides. Used to recover an official
    romanized song/artist (and sometimes the anime) name."""
    open_fields = {key for key in FIELDS if not guess.get(key)}
    if not open_fields or not snippets:
        return guess

    known = ", ".join(f"{key}: {guess.get(key) or '(unknown)'}" for key in FIELDS)
    prompt = (
        "You are finding the official romanized name for anime song fields that are "
        "still unknown.\n"
        f"Video title (context only): {title}\n"
        f"Known so far: {known}\n"
        f"You may ONLY fill: {', '.join(sorted(open_fields))}. Leave everything else as is.\n\n"
        "iTunes catalog matches, one per line as `artist - track (album)`:\n"
        + "\n".join(f"- {s}" for s in snippets)
        + "\n\n"
        "If one entry clearly refers to THIS video's song, copy its romanized artist and "
        "track. The album field often names the anime (\"X Original Soundtrack\", "
        "\"Song (From \\\"X\\\")\"). "
        f"{ROMANIZATION_RULE} "
        "If nothing clearly matches an open field, leave it \"\" - a wrong name is worse "
        "than a blank one. Never reuse a word from the video title (Opening, OP, ED, a "
        "number) as a song title.\n"
        'Reply with ONLY JSON: {"anime": "", "song": "", "artist": ""}'
    )

    try:
        parsed = extract_json(call_llm(prompt))
    except Exception:
        return guess

    result = dict(guess)
    for key in open_fields:
        value = parsed.get(key)
        if value and not _is_junk(str(value)):
            result[key] = str(value)
    return result


def _stash_and_clear_japanese(guess, stash):
    """A kanji/kana-only answer isn't good enough yet - park it in `stash`
    (first one wins) and blank the field so the next step still gets a
    chance to find a romanized version."""
    for key in FIELDS:
        if is_japanese(guess.get(key)):
            stash.setdefault(key, guess[key])
            guess[key] = ""
    return guess


def resolve_anime_name(japanese_anime):
    """Look up a Japanese anime title against AniList to get its official
    English/romaji name. A deterministic database lookup, not an LLM guess -
    AniList matches native titles directly, so no hallucination risk."""
    try:
        candidates = search_anime_cover(japanese_anime)
    except Exception:
        return None
    return candidates[0]["track"] if candidates else None


def ai_guess_with_search(video_id, title, hint, description=None):
    hint = dict(hint or {})

    if description is None:
        # Search tab: fetch it now. (The playlist flow already has it from the
        # prefetch and passes it in.) A rate-limit or a dead video has to reach
        # the caller; anything else, carry on with just the title.
        try:
            description = get_video_description(video_id)
        except (RateLimitedError, VideoUnavailableError):
            raise
        except Exception:
            description = ""

    raw = ai_extract_metadata(title, description, hint)
    working = {
        "anime": str(raw.get("anime") or "").strip(),
        "type": str(raw.get("type") or hint.get("type") or "OP").upper(),
        "number": str(raw.get("number") or hint.get("number") or "").strip(),
        "song": strip_type_labels(str(raw.get("song") or "")).strip(),
        "artist": str(raw.get("artist") or "").strip(),
    }
    # Drop a type label the model echoed back as a name.
    for key in ("song", "artist"):
        if _is_junk(working[key]):
            working[key] = ""

    # Park anything still in Japanese script and blank it so the online
    # lookups below can try for a romanized version.
    stash = {}
    working = _stash_and_clear_japanese(working, stash)

    # Anime name still Japanese -> AniList's database (authoritative romaji).
    if not working["anime"] and stash.get("anime"):
        resolved = resolve_anime_name(stash["anime"])
        if resolved:
            working["anime"] = resolved
            stash.pop("anime", None)

    # Song/artist still missing or Japanese -> iTunes catalog search. Query
    # with whatever we have; a resolved artist name is the strongest hint.
    if not _all_resolved(working):
        query = " ".join(
            filter(
                None,
                [
                    working.get("artist") or stash.get("artist"),
                    working.get("song") or stash.get("song"),
                    working.get("anime") or stash.get("anime"),
                ],
            )
        ).strip()
        if not query:
            query = re.sub(r"[|｜\[\]()]", " ", title).strip()

        snippets = itunes_song_snippets(query) if query else []
        known_anime = working.get("anime") or stash.get("anime")
        if known_anime:
            snippets = [s for s in snippets if _mentions_anime(known_anime, s)]
        if snippets:
            working = _stash_and_clear_japanese(
                ai_romanize_from_itunes(title, working, snippets), stash
            )

    # Nothing romanized found anywhere - a kanji/kana answer beats no answer.
    for key in FIELDS:
        if not working.get(key) and stash.get(key):
            working[key] = stash[key]

    if working.get("anime"):
        working["anime"] = strip_type_labels(working["anime"])
    if working.get("song"):
        working["song"] = strip_type_labels(working["song"])
    return working
