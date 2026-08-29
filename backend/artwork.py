"""Cover art sources: AniList for actual anime poster/key art, iTunes for
song/album covers (used as the fallback candidates, and as a stand-in
"search engine" for song/artist metadata in ai_guess.py)."""

import json
import re
import urllib.parse
import urllib.request


def search_artwork(query, limit=8):
    params = urllib.parse.urlencode({"term": query, "media": "music", "limit": limit})
    request_url = f"https://itunes.apple.com/search?{params}"
    with urllib.request.urlopen(request_url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    candidates = []
    for result in data.get("results", []) or []:
        art = result.get("artworkUrl100")
        if not art:
            continue
        art_hd = re.sub(r"/\d+x\d+bb\.(jpg|png)$", r"/600x600bb.\1", art)
        candidates.append(
            {
                "artwork_url": art_hd,
                "track": result.get("trackName", ""),
                "artist": result.get("artistName", ""),
                "collection": result.get("collectionName", ""),
            }
        )
    return candidates


ANILIST_QUERY = """
query ($search: String) {
  Page(page: 1, perPage: 5) {
    media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
      title { romaji english }
      coverImage { extraLarge }
    }
  }
}
"""


def search_anime_cover(anime_name):
    """AniList's anime database - actual show poster/key art, unlike iTunes
    which only ever has music single/album covers."""
    if not anime_name.strip():
        return []
    body = json.dumps({"query": ANILIST_QUERY, "variables": {"search": anime_name}}).encode("utf-8")
    req = urllib.request.Request(
        "https://graphql.anilist.co",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    candidates = []
    for media in (data.get("data", {}).get("Page", {}).get("media") or []):
        art = (media.get("coverImage") or {}).get("extraLarge")
        if not art:
            continue
        title = media.get("title") or {}
        candidates.append(
            {
                "artwork_url": art,
                "track": title.get("english") or title.get("romaji") or anime_name,
                "artist": "",
                "collection": "Anime poster",
            }
        )
    return candidates
