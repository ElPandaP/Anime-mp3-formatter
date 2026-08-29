"""AI-assisted title/metadata resolution, escalating through progressively
more expensive sources: video title -> video description -> iTunes catalog
search. See ai_guess_with_search for the escalation chain. This applies to
anime/song/artist alike - a playlist item has no search-query hint the way a
"Search song" result does, so every field needs its own way to be verified
or recovered if the title alone doesn't give it up."""

import re

from artwork import search_anime_cover, search_artwork
from japanese_text import ROMANIZATION_RULE, is_japanese, strip_japanese
from llm_client import call_llm, extract_json
from youtube import get_video_description

FIELDS = ("anime", "song", "artist")


def ai_guess_titles(titles):
    prompt = (
        "You extract anime song metadata from YouTube video titles.\n"
        "For each numbered title below, identify:\n"
        "- anime: the anime's name only (no season/episode filler words unless "
        "they're part of the title itself, e.g. keep 'Season 2').\n"
        "- type: OP, ED, or OST.\n"
        "- number: ONLY a plain numeral if the title shows one (e.g. \"2\"). "
        "Words like Full, Short, TV, NCOP, NCED, ver are NOT numbers - use \"\" instead.\n"
        "- song: the clean song title, with quote marks, brackets (『』「」\"\"''), "
        "and filler words like Full/Short/Lyrics/HD/Creditless stripped out.\n"
        "- artist: the performing artist/band, if named anywhere in the title.\n"
        f"{ROMANIZATION_RULE}\n"
        'Use "" for any field you cannot determine.\n\n'
        "Example input:\n"
        '1. Attack on Titan S4 - Opening 1 Full『My War』by SiM [Lyrics]\n'
        '2. | Some Anime Title | ED FULL | [LYRICS] |\n'
        "Example output:\n"
        '[{"anime": "Attack on Titan S4", "type": "OP", "number": "1", '
        '"song": "My War", "artist": "SiM"}, '
        '{"anime": "Some Anime Title", "type": "ED", "number": "", '
        '"song": "", "artist": ""}]\n\n'
        "Reply with ONLY a JSON array of objects, in the same order as the "
        "titles below, one object per title, no prose, no markdown.\n\n"
        + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    )

    parsed = extract_json(call_llm(prompt), "[", "]")

    results = []
    for i in range(len(titles)):
        item = parsed[i] if i < len(parsed) and isinstance(parsed[i], dict) else {}
        results.append(
            {
                "anime": strip_japanese(str(item.get("anime") or "")),
                "type": str(item.get("type") or "OP").upper(),
                "number": str(item.get("number") or ""),
                "song": strip_japanese(str(item.get("song") or "")),
                "artist": strip_japanese(str(item.get("artist") or "")),
            }
        )
    return results


def itunes_song_snippets(query, max_results=200):
    """iTunes's catalog as a stand-in for a general web search: no API key,
    no bot-detection wall (unlike scraping a search engine), and it already
    stores properly romanized official artist/track names - plus the anime
    name itself often shows up right in the collection/album title (e.g.
    "Song (From "Attack on Titan")" or "Attack on Titan Original Soundtrack")."""
    try:
        candidates = search_artwork(query, limit=max_results)
    except Exception:
        return []
    return [
        f"{c['artist']} - {c['track']} ({c.get('collection', '')})"
        for c in candidates
        if c.get("track")
    ]


def _all_resolved(guess):
    return all(guess.get(key) for key in FIELDS)


# Matches video-annotation/type-label text that is never a real song/artist/
# anime name (a "Full"/"[4K]" tag, or the OP/ED label itself with an
# optional number, e.g. "Opening 1", "OP", "ED FULL"). Used both to decide
# if an existing value is unreliable enough to override, and to reject an
# AI answer that's just this kind of label rather than a real name - the
# local model sometimes echoes the type label back as if it were the song
# title instead of admitting it doesn't know.
JUNK_VALUE_RE = re.compile(
    r"^(op|opening|ed|ending|ost|soundtrack|nc\s*op|nc\s*ed|ncop|nced|creditless|"
    r"full|short|hd|4k|8k|uhd|tv\s*size|\d+\s*fps)\.?\s*\d*$",
    re.IGNORECASE,
)


def _is_junk(value):
    return bool(value) and bool(JUNK_VALUE_RE.match(value.strip()))


def _mentions_anime(anime, snippet):
    """Loose keyword check: does this iTunes snippet's text plausibly refer
    to the anime we already know? iTunes's fuzzy search can return a single,
    completely unrelated "closest match" for an obscure/romanized query
    (e.g. searching "Kami Nomi zo Shiru Sekai" once returned only "Black
    Catcher (From Black Clover)") - the LLM tends to accept whatever it's
    given rather than notice it doesn't fit, so filter those out first.
    Works for a still-Japanese anime name too - iTunes snippets often embed
    the native-script title verbatim (e.g. "【山田くんと7人の魔女】") even when
    the query itself was in Japanese, so check for that as well."""
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


SONG_HINT_RE = re.compile(r"(song|artist|singer|vocal|\bby\b|[「『\"'‘’])", re.IGNORECASE)


def _context_hints_song_info(context_text):
    """Song/artist extraction needs an actual textual hint (a label, quote
    marks, "by X") somewhere in the context - a description with none of
    that (e.g. a one-line "1st opening of X" note with zero real info) gives
    the model nothing legitimate to extract, and it tends to just echo the
    unrelated prose back as if it were the answer instead of saying "" ."""
    return bool(SONG_HINT_RE.search(context_text))


def _open_fields(base_guess, allow_override):
    """Which fields this call is allowed to change: always an empty one: also
    a filled one, but only if `allow_override` is set AND the current value
    looks like a misread annotation rather than a plausible real name - a
    long, messy description can mention other credits (other songs, other
    collabs) that don't apply to this video, so an already-plausible value
    is never up for replacement."""
    return {
        key
        for key in FIELDS
        if not base_guess.get(key) or (allow_override and _is_junk(base_guess.get(key)))
    }


def ai_fill_from_context(title, base_guess, context_label, context_text, allow_override=False):
    base_guess = dict(base_guess or {})
    if not context_text:
        return base_guess

    open_fields = _open_fields(base_guess, allow_override)
    if not _context_hints_song_info(context_text):
        open_fields = open_fields - {"song", "artist"}
    if not open_fields:
        return base_guess

    fields_line = ", ".join(f"{key}: {base_guess.get(key) or '(unknown)'}" for key in FIELDS)
    only_line = (
        f"You may ONLY report a value for: {', '.join(sorted(open_fields))}. "
        f"The rest are already confirmed correct - do not repeat or second-guess them.\n"
        if len(open_fields) < len(FIELDS)
        else ""
    )

    prompt = (
        "You are extracting anime song metadata using extra context.\n"
        f"Original YouTube video title (shown ONLY for background - it has ALREADY "
        f"been analyzed and did NOT clearly state the open field(s) below; do not "
        f"re-derive an answer from it): {title}\n"
        f"Current guess: {fields_line}\n"
        f"{only_line}"
        "A long description can mention OTHER songs, albums, or collaborators that have "
        "nothing to do with this specific video - only use a name/title that clearly "
        "refers to THIS video's own anime/song/artist, not a credit for something else "
        "mentioned in passing.\n\n"
        f"{context_label}:\n{context_text[:2000]}\n\n"
        "If, and ONLY if, the context above EXPLICITLY states a value for one of the "
        "open fields, report it. Look for:\n"
        "- Anime: after \"Anime:\", a collection/album name like 'Song (From \"X\")', "
        "'X Original Soundtrack', 'X OP/ED', or the show clearly named in a track listing.\n"
        "- Song/artist: after \"Song:\", \"Artist:\", \"Song Title :\", \"by\", a track "
        "listing, or an obvious name in a URL like lnk.to/artistname.\n"
        "Copy or lightly clean up the exact name found - never translate the meaning of "
        "a Japanese word/phrase into English (e.g. a title like \"春擬き\" must stay as "
        "its actual name if you find one, not be translated to something like \"Spring "
        "Proposal\"). If the context gives BOTH a Japanese-script version and a "
        "romanized/English version of the same name (e.g. a Japanese line followed by an "
        "English translation of it, as is common in official descriptions), always report "
        f"the romanized/English one, never the Japanese-script one. {ROMANIZATION_RULE} "
        "Getting this wrong is worse than leaving it blank: if the context "
        "above does not CLEARLY and EXPLICITLY state an open field, you MUST leave it "
        "\"\" - never guess, never invent a plausible-sounding name, and never reuse "
        "words from the video title (like \"Opening\", \"OP\", \"ED\" or a number) as if "
        "they were a song title.\n"
        'Reply with ONLY JSON: {"anime": "", "song": "", "artist": ""} - use "" for '
        "anything still unknown or not open for change.\n"
    )

    try:
        parsed = extract_json(call_llm(prompt), "{", "}")
    except Exception:
        return base_guess

    result = dict(base_guess)
    for key in open_fields:
        value = parsed.get(key)
        # The model sometimes echoes a type label (e.g. "Opening 1", "OP")
        # back as if it were the actual name, rather than admitting it
        # couldn't find one in the context - never accept that as real.
        if value and not _is_junk(str(value)):
            result[key] = str(value)
    return result


def _stash_and_clear_japanese(guess, stash):
    """A kanji/kana-only answer isn't good enough yet - park it in `stash`
    (the first one found is kept) and blank the field so the next, more
    capable step still gets a chance to find a romanized version."""
    for key in FIELDS:
        if is_japanese(guess.get(key)):
            stash.setdefault(key, guess[key])
            guess[key] = ""
    return guess


def resolve_anime_name(japanese_anime):
    """Look up a Japanese anime title against AniList's database to get its
    official English/romaji name. This is a deterministic database lookup,
    not an LLM guess - AniList's search matches native titles directly, so
    it doesn't carry the hallucination risk of asking the model to recall
    or translate the title from memory (which can misremember, e.g. saying
    "Yamato-kun" instead of "Yamada-kun")."""
    try:
        candidates = search_anime_cover(japanese_anime)
    except Exception:
        return None
    return candidates[0]["track"] if candidates else None


def ai_guess_with_search(video_id, title, base_guess):
    stash = {}
    working = _stash_and_clear_japanese(dict(base_guess or {}), stash)

    # 0. If the anime name is still in Japanese, resolve it against
    # AniList's anime database first - real, authoritative data beats
    # anything the LLM stages below might come up with for this field.
    if not working.get("anime") and stash.get("anime"):
        resolved_anime = resolve_anime_name(stash["anime"])
        if resolved_anime:
            working["anime"] = resolved_anime
            stash.pop("anime", None)

    # 1. The video's own description often has explicit "Anime: X / Song: Y /
    # Artist: Z" credits - always worth checking, even if fields already
    # look filled in, since a guess might just be a misread bracketed
    # annotation (e.g. "[Creditless]") or a missing anime name. The
    # description is authoritative enough to correct that.
    try:
        description = get_video_description(video_id)
    except Exception:
        description = ""
    working = _stash_and_clear_japanese(
        ai_fill_from_context(title, working, "Video description", description, allow_override=True),
        stash,
    )
    if _all_resolved(working):
        return working

    # 2. Still missing something - search iTunes's catalog, which stores
    # official romanized artist/track names and often the anime name too
    # (in the collection/album field). Use whatever we already have (a
    # resolved artist name is the strongest hint) to narrow it down. This
    # stage only fills gaps - it's less authoritative than an explicit
    # description credit, so it never overrides an existing guess.
    # Prefer what's already romanized (`working`); fall back to the stashed
    # kanji/kana (`stash`) if that's all we have - iTunes snippets often
    # embed the native-script title verbatim, so a Japanese query can still
    # find the right entry. Either way, _mentions_anime below (which
    # understands both scripts) is what actually keeps bad matches out, not
    # the choice of query language.
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

    snippets = []
    if query:
        try:
            snippets = itunes_song_snippets(query)
        except Exception:
            snippets = []

    known_anime = working.get("anime") or stash.get("anime")
    if known_anime:
        snippets = [s for s in snippets if _mentions_anime(known_anime, s)]

    if snippets:
        working = _stash_and_clear_japanese(
            ai_fill_from_context(
                title, working, "iTunes catalog matches", "\n".join(f"- {s}" for s in snippets)
            ),
            stash,
        )

    # Nothing romanized was found anywhere - a kanji/kana answer beats no
    # answer, so fall back to whatever we stashed along the way.
    for key in FIELDS:
        if not working.get(key) and stash.get(key):
            working[key] = stash[key]
    return working
