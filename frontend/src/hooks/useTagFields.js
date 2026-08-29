import { useEffect, useRef, useState } from "react";
import { searchArtwork } from "../api";
import { buildPreview } from "../utils";

export function useTagFields(guess = {}) {
  const [anime, setAnime] = useState(guess.anime || "");
  const [type, setType] = useState(guess.type || "OP");
  const [number, setNumber] = useState(guess.number || "");
  const [song, setSong] = useState(guess.song || "");
  const [artist, setArtist] = useState(guess.artist || "");
  const [artworkUrl, setArtworkUrlState] = useState(null);
  const [artworkCandidates, setArtworkCandidates] = useState([]);
  const [artworkLoading, setArtworkLoading] = useState(false);
  const [artworkError, setArtworkError] = useState(null);

  const artworkTouched = useRef(false);

  const setArtworkUrl = (url) => {
    artworkTouched.current = true;
    setArtworkUrlState(url);
  };

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

  async function findArtwork() {
    const query = anime.trim() || `${artist} ${song}`.trim();
    const results = await runArtworkSearch(query);
    if (results[0]) setArtworkUrl(results[0].artwork_url);
  }

  // Auto-search cover art by anime name (song/artist come from the selected
  // video's own guess instead, so they stay specific to what was picked).
  useEffect(() => {
    if (!anime.trim()) return undefined;
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
    findArtwork,
    preview,
  };
}
