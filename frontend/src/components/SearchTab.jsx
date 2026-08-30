import { useState } from "react";
import { searchVideos } from "../lib/api";
import { parseAnimeQuery } from "../lib/utils";
import { resolveItemTags } from "../lib/resolveTags";
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
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSelect(item) {
    setSelected(item);
    setEnrichingId(item.id);

    // The search box text (e.g. "86 ed 2") is a strong hint for
    // anime/type/number - the AI gets it and everything else from the
    // video's own title and description.
    const { finalGuess, artworkUrl, artworkCandidates } = await resolveItemTags(item, queryGuess, aiEnabled);

    setAiGuesses((prev) => ({ ...prev, [item.id]: finalGuess }));
    // Resolve cover art too, before revealing the panel - so nothing pops in
    // or changes after the form is already showing.
    if (artworkUrl || artworkCandidates.length) {
      setArtworkPrefetch((prev) => ({ ...prev, [item.id]: { url: artworkUrl, candidates: artworkCandidates } }));
    }

    setEnrichingId((current) => (current === item.id ? null : current));
  }

  return (
    <div>
      <div className="row">
        <input
          type="text"
          placeholder="E.g. frieren ed 2"
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
