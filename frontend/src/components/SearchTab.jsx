import { useState } from "react";
import { searchVideos, getAiGuesses, getAiGuessOnline } from "../api";
import { parseAnimeQuery, mergeGuesses } from "../utils";
import TagForm from "./TagForm";
import ResultCard from "./ResultCard";

export default function SearchTab({ outputDir, aiEnabled }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [queryGuess, setQueryGuess] = useState(null);
  const [aiGuesses, setAiGuesses] = useState({});
  const [enrichingId, setEnrichingId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function runSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setSelected(null);
    setAiGuesses({});
    try {
      const data = await searchVideos(query);
      setResults(data.results);
      setQueryGuess(parseAnimeQuery(query));
      if (aiEnabled) fetchAiGuesses(data.results);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function fetchAiGuesses(items) {
    try {
      const data = await getAiGuesses(items.map((item) => item.title));
      // Merge rather than replace: a per-item online enrichment (triggered by
      // selecting a result) may have already resolved for one of these ids
      // by the time this batch call comes back - don't clobber it with the
      // weaker title-only guess.
      setAiGuesses((prev) => {
        const next = { ...prev };
        items.forEach((item, i) => {
          next[item.id] = mergeGuesses(data.results[i], prev[item.id]);
        });
        return next;
      });
    } catch {
      // AI parsing is optional (needs LLM_API_KEY configured) - silently
      // fall back to rule-based guessing when it's unavailable or fails.
    }
  }

  async function handleSelect(item) {
    setSelected(item);
    if (!aiEnabled) return;

    // Always check the video description, even if song/artist already look
    // filled in - that guess might just be a misread title fragment (e.g. a
    // "[Creditless]" annotation), and the description can correct it.
    const merged = mergeGuesses(item.guess, queryGuess, aiGuesses[item.id]);
    setEnrichingId(item.id);
    try {
      const data = await getAiGuessOnline(item.id, item.title, merged);
      setAiGuesses((prev) => ({ ...prev, [item.id]: mergeGuesses(prev[item.id], data.result) }));
    } catch {
      // Best-effort enrichment (description/web search) - ignore failures.
    } finally {
      setEnrichingId((current) => (current === item.id ? null : current));
    }
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
      <div className="search-side">
        {!selected && <div className="tag-form side-placeholder">Select a result to edit its tags</div>}
        {selected && enrichingId === selected.id && (
          <div className="tag-form side-loading">
            <span className="spinner-large" />
            <p>Looking up song/artist...</p>
          </div>
        )}
        {selected && enrichingId !== selected.id && (
          <TagForm
            key={selected.id}
            video={selected}
            outputDir={outputDir}
            queryGuess={queryGuess}
            aiGuess={aiGuesses[selected.id]}
          />
        )}
      </div>
    </div>
  );
}
