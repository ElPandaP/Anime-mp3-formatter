import { useState } from "react";
import { searchVideos } from "../api";
import { parseAnimeQuery } from "../utils";
import TagForm from "./TagForm";
import ResultCard from "./ResultCard";

export default function SearchTab({ outputDir }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [queryGuess, setQueryGuess] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function runSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setSelected(null);
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

  return (
    <div className="search-layout">
      <div className="search-main">
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
            <ResultCard key={item.id} item={item} onSelect={setSelected} />
          ))}
        </div>
      </div>
      {selected && (
        <div className="search-side">
          <TagForm key={selected.id} video={selected} outputDir={outputDir} queryGuess={queryGuess} />
        </div>
      )}
    </div>
  );
}
