import { useRef, useState } from "react";
import { loadPlaylist, downloadPlaylist } from "../api";
import PlaylistRow from "./PlaylistRow";

export default function PlaylistTab({ outputDir }) {
  const [url, setUrl] = useState("");
  const [items, setItems] = useState([]);
  const [bulkAnime, setBulkAnime] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [summary, setSummary] = useState(null);
  const rowRefs = useRef([]);

  async function handleLoad() {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    setSummary(null);
    try {
      const data = await loadPlaylist(url);
      setItems(data.items);
      rowRefs.current = [];
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function applyBulkAnime() {
    rowRefs.current.forEach((r) => r && r.setAnime(bulkAnime));
  }

  async function handleDownloadAll() {
    const payload = rowRefs.current.filter(Boolean).map((r) => r.getData());
    setDownloading(true);
    setSummary(null);
    try {
      const data = await downloadPlaylist(payload, outputDir);
      let ok = 0;
      data.results.forEach((r, i) => {
        if (r.success) ok++;
        if (rowRefs.current[i]) rowRefs.current[i].setResult(r);
      });
      setSummary(`Done: ${ok}/${data.results.length} downloaded successfully.`);
    } catch (err) {
      setSummary(err.message);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div>
      <div className="row">
        <input
          type="text"
          placeholder="YouTube playlist URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button onClick={handleLoad} disabled={loading}>
          {loading ? "Loading..." : "Load playlist"}
        </button>
      </div>
      {error && <span className="status error">{error}</span>}

      {items.length > 0 && (
        <div className="row bulk-row">
          <input
            type="text"
            placeholder="Anime name (apply to all rows)"
            value={bulkAnime}
            onChange={(e) => setBulkAnime(e.target.value)}
          />
          <button onClick={applyBulkAnime}>Apply to all</button>
          <button onClick={handleDownloadAll} disabled={downloading}>
            {downloading ? "Downloading..." : "Download all"}
          </button>
        </div>
      )}

      <div className="playlist-items">
        {items.map((item, i) => (
          <PlaylistRow key={item.id} video={item} ref={(el) => (rowRefs.current[i] = el)} />
        ))}
      </div>
      {summary && <div className="status ok">{summary}</div>}
    </div>
  );
}
