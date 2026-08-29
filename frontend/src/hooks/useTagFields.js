import { useEffect, useRef, useState } from "react";
import { searchArtwork } from "../api";
import { buildPreview } from "../utils";

const FIELDS = ["anime", "type", "number", "song", "artist"];

export function useTagFields(guess = {}) {
  const [anime, setAnimeState] = useState(guess.anime || "");
  const [type, setTypeState] = useState(guess.type || "OP");
  const [number, setNumberState] = useState(guess.number || "");
  const [song, setSongState] = useState(guess.song || "");
  const [artist, setArtistState] = useState(guess.artist || "");
  const [artworkUrl, setArtworkUrlState] = useState(null);
  const [artworkCandidates, setArtworkCandidates] = useState([]);
  const [artworkLoading, setArtworkLoading] = useState(false);
  const [artworkError, setArtworkError] = useState(null);

  const touched = useRef({ anime: false, type: false, number: false, song: false, artist: false });
  const artworkTouched = useRef(false);

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
