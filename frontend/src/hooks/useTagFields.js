import { useEffect, useRef, useState } from "react";
import { searchArtwork } from "../api";
import { buildPreview } from "../utils";

const FIELDS = ["anime", "type", "number", "song", "artist"];

export function useTagFields(guess = {}, initialArtwork = null) {
  const [anime, setAnimeState] = useState(guess.anime || "");
  const [type, setTypeState] = useState(guess.type || "OP");
  const [number, setNumberState] = useState(guess.number || "");
  const [song, setSongState] = useState(guess.song || "");
  const [artist, setArtistState] = useState(guess.artist || "");
  const [artworkUrl, setArtworkUrlState] = useState(initialArtwork?.url ?? null);
  const [artworkCandidates, setArtworkCandidates] = useState(initialArtwork?.candidates ?? []);
  const [artworkLoading, setArtworkLoading] = useState(false);
  const [artworkError, setArtworkError] = useState(null);

  const touched = useRef({ anime: false, type: false, number: false, song: false, artist: false });
  const artworkTouched = useRef(false);
  // The caller (SearchTab) already resolved cover art for this exact anime
  // value before showing the form at all - skip auto-searching again for
  // that same value. Compared by value (not a one-shot flag) so React 19's
  // StrictMode double-invoking this effect in dev doesn't re-trigger it.
  const prefetchedAnime = useRef(initialArtwork ? guess.anime || "" : null);

  const setters = { anime: setAnimeState, type: setTypeState, number: setNumberState, song: setSongState, artist: setArtistState };
  const makeSetter = (key) => (value) => {
    touched.current[key] = true;
    setters[key](value);
  };
  const setAnime = makeSetter("anime");
  const setType = makeSetter("type");
  const setNumber = makeSetter("number");
  const setSong = makeSetter("song");
  const setArtist = makeSetter("artist");

  const setArtworkUrl = (url) => {
    artworkTouched.current = true;
    setArtworkUrlState(url);
  };

  // A better guess (e.g. from an AI title parse) can arrive after the user
  // has already started editing. Only fill in fields they haven't touched.
  useEffect(() => {
    for (const key of FIELDS) {
      if (guess[key] && !touched.current[key]) setters[key](guess[key]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guess]);

  const preview = buildPreview(anime, type, number, song);

  async function runArtworkSearch(query) {
    if (!query.trim()) return [];
    setArtworkLoading(true);
    setArtworkError(null);
    try {
      const data = await searchArtwork(query);
      setArtworkCandidates(data.results);
      return data.results;
    } catch (err) {
      setArtworkError(err.message);
      return [];
    } finally {
      setArtworkLoading(false);
    }
  }

  // Auto-search cover art by anime name (song/artist come from the selected
  // video's own guess instead, so they stay specific to what was picked).
  useEffect(() => {
    if (!anime.trim()) return undefined;
    if (anime === prefetchedAnime.current) return undefined;
    const timer = setTimeout(async () => {
      const results = await runArtworkSearch(anime.trim());
      if (!results.length) return;
      if (!artworkTouched.current) setArtworkUrlState(results[0].artwork_url);
    }, 500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anime]);

  return {
    anime,
    setAnime,
    type,
    setType,
    number,
    setNumber,
    song,
    setSong,
    artist,
    setArtist,
    artworkUrl,
    setArtworkUrl,
    artworkCandidates,
    artworkLoading,
    artworkError,
    preview,
  };
}
