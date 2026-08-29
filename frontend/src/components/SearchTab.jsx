import { useRef, useState } from "react";
import { searchVideos, getAiGuesses, getAiGuessOnline, searchArtwork } from "../api";
import { parseAnimeQuery, mergeGuesses } from "../utils";
import TagForm from "./TagForm";
import ResultCard from "./ResultCard";

export default function SearchTab({ outputDir, aiEnabled }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [queryGuess, setQueryGuess] = useState(null);
  const [aiGuesses, setAiGuesses] = useState({});
  const [artworkPrefetch, setArtworkPrefetch] = useState({});
  const [enrichingId, setEnrichingId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // The batch title guess (covering every result) runs independently of
  // selection. If it resolves an anime name *after* a quick click already
  // started the per-item lookup below, that name would otherwise arrive
  // post-reveal and trigger a late, visible cover-art search. Awaiting this
  // in handleSelect keeps everything inside the single loading gate.
  const batchGuessPromise = useRef(Promise.resolve({}));

  async function runSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setSelected(null);
    setAiGuesses({});
    setArtworkPrefetch({});
    try {
      const data = await searchVideos(query);
      setResults(data.results);
      setQueryGuess(parseAnimeQuery(query));
      batchGuessPromise.current = aiEnabled ? fetchAiGuesses(data.results) : Promise.resolve({});
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function fetchAiGuesses(items) {
    try {
      const data = await getAiGuesses(items.map((item) => item.title));
      const byId = {};
      items.forEach((item, i) => {
        byId[item.id] = data.results[i];
      });
      // Merge rather than replace: a per-item online enrichment (triggered by
      // selecting a result) may have already resolved for one of these ids
      // by the time this batch call comes back - don't clobber it with the
      // weaker title-only guess.
      setAiGuesses((prev) => {
        const next = { ...prev };
        items.forEach((item) => {
          next[item.id] = mergeGuesses(byId[item.id], prev[item.id]);
        });
        return next;
      });
      return byId;
    } catch {
      // AI parsing is optional (needs LLM_API_KEY configured) - silently
      // fall back to rule-based guessing when it's unavailable or fails.
      return {};
    }
  }

  async function handleSelect(item) {
    setSelected(item);
    setEnrichingId(item.id);

    const batchGuesses = await batchGuessPromise.current;

    // Always check the video description, even if song/artist already look
    // filled in - that guess might just be a misread title fragment (e.g. a
    // "[Creditless]" annotation), and the description can correct it.
    let finalGuess = mergeGuesses(item.guess, queryGuess, batchGuesses[item.id], aiGuesses[item.id]);
    if (aiEnabled) {
      try {
        const data = await getAiGuessOnline(item.id, item.title, finalGuess);
        finalGuess = mergeGuesses(finalGuess, data.result);
        setAiGuesses((prev) => ({ ...prev, [item.id]: mergeGuesses(prev[item.id], data.result) }));
      } catch {
        // Best-effort enrichment (description/web search) - ignore failures.
      }
    }

    // Resolve cover art too, before revealing the panel - so nothing pops in
    // or changes after the form is already showing.
    if (finalGuess.anime) {
      try {
        const artData = await searchArtwork(finalGuess.anime);
        setArtworkPrefetch((prev) => ({
          ...prev,
          [item.id]: { url: artData.results[0]?.artwork_url ?? null, candidates: artData.results },
        }));
      } catch {
        // No cover art found - the form's own picker can still be used manually.
      }
    }

    setEnrichingId((current) => (current === item.id ? null : current));
  }

  return (
    <div>
      <div className="row">
        <input
          type="text"
          placeholder="E.g. mushoku tensei op 1"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runSearch()}
        />
        <button onClick={runSearch} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </div>
      {error && <span className="status error">{error}</span>}
      <div className="results">
        {results.map((item) => (
          <ResultCard key={item.id} item={item} onSelect={handleSelect} />
        ))}
      </div>
      <div className="edit-panel">
        {!selected && <div className="tag-form side-placeholder">Select a result to edit its tags</div>}
        {selected && enrichingId === selected.id && (
          <div className="tag-form side-loading">
            <span className="spinner-large" />
            <p>Loading song, artist and cover art...</p>
          </div>
        )}
        {selected && enrichingId !== selected.id && (
          <TagForm
            key={selected.id}
            video={selected}
            outputDir={outputDir}
            queryGuess={queryGuess}
            aiGuess={aiGuesses[selected.id]}
            initialArtwork={artworkPrefetch[selected.id]}
          />
        )}
      </div>
    </div>
  );
}
