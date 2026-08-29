import { useState } from "react";
import { loadPlaylist, downloadPlaylist } from "../api";
import { resolveItemTags } from "../resolveTags";
import PlaylistRow from "./PlaylistRow";
import TagForm from "./TagForm";

export default function PlaylistTab({ outputDir, aiEnabled }) {
  const [url, setUrl] = useState("");
  const [items, setItems] = useState([]);
  const [itemData, setItemData] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [loadingPlaylist, setLoadingPlaylist] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [preparedCount, setPreparedCount] = useState(0);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [results, setResults] = useState({});
  const [summary, setSummary] = useState(null);

  async function handleLoad() {
    if (!url.trim()) return;
    setLoadingPlaylist(true);
    setError(null);
    setSummary(null);
    setResults({});
    setItems([]);
    setItemData({});
    setEditingId(null);
    try {
      const data = await loadPlaylist(url);
      setItems(data.items);
      setLoadingPlaylist(false);
      prepareAllItems(data.items);
    } catch (err) {
      setError(err.message);
      setLoadingPlaylist(false);
    }
  }

  async function prepareAllItems(playlistItems) {
    setPreparing(true);
    setPreparedCount(0);

    for (const item of playlistItems) {
      const { finalGuess, artworkUrl, artworkCandidates } = await resolveItemTags(item, null, aiEnabled);

      const resolved = {
        anime: finalGuess.anime || "",
        type: finalGuess.type || "OP",
        number: finalGuess.number || "",
        song: finalGuess.song || "",
        artist: finalGuess.artist || "",
        artworkUrl,
        artworkCandidates,
      };
      setItemData((prev) => ({ ...prev, [item.id]: resolved }));
      setPreparedCount((c) => c + 1);
    }

    setPreparing(false);
  }

  function handleSaveEdit(values) {
    setItemData((prev) => ({ ...prev, [editingId]: values }));
    setEditingId(null);
  }

  async function handleDownloadAll() {
    setDownloading(true);
    setSummary(null);
    const payload = items.map((item) => {
      const data = itemData[item.id] || {};
      return {
        id: item.id,
        anime: data.anime || "",
        type: data.type || "OP",
        number: data.number || "",
        song: data.song || "",
        artist: data.artist || "",
        artwork_url: data.artworkUrl || null,
      };
    });

    try {
      const data = await downloadPlaylist(payload, outputDir);
      const resultsById = {};
      let ok = 0;
      data.results.forEach((r) => {
        resultsById[r.id] = r;
        if (r.success) ok++;
      });
      setResults(resultsById);
      setSummary(`Done: ${ok}/${data.results.length} downloaded successfully.`);
    } catch (err) {
      setSummary(err.message);
    } finally {
      setDownloading(false);
    }
  }

  const editingItem = editingId ? items.find((item) => item.id === editingId) : null;

  return (
    <div>
      <div className="row">
        <input
          type="text"
          placeholder="YouTube playlist URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button onClick={handleLoad} disabled={loadingPlaylist || preparing}>
          {loadingPlaylist ? "Loading..." : "Load playlist"}
        </button>
      </div>
      {error && <span className="status error">{error}</span>}

      {preparing && (
        <div className="prepare-status">
          <span className="spinner-large" />
          <p>
            Preparing tags: {preparedCount}/{items.length}...
          </p>
        </div>
      )}

      {!preparing && items.length > 0 && (
        <>
          <div className="row playlist-actions">
            <button onClick={handleDownloadAll} disabled={downloading}>
              {downloading ? "Downloading..." : "Download all"}
            </button>
          </div>

          <div className="playlist-items">
            {items.map((item) => (
              <PlaylistRow
                key={item.id}
                video={item}
                data={itemData[item.id]}
                status={
                  results[item.id]
                    ? {
                        ok: results[item.id].success,
                        text: results[item.id].success ? "OK" : results[item.id].error,
                      }
                    : null
                }
                onEdit={() => setEditingId(item.id)}
              />
            ))}
          </div>
          {summary && <div className="status ok">{summary}</div>}
        </>
      )}

      {editingItem && (
        <div className="edit-panel">
          <TagForm
            key={editingItem.id}
            video={editingItem}
            queryGuess={null}
            aiGuess={itemData[editingItem.id]}
            initialArtwork={{
              url: itemData[editingItem.id]?.artworkUrl ?? null,
              candidates: itemData[editingItem.id]?.artworkCandidates ?? [],
            }}
            onSave={handleSaveEdit}
          />
        </div>
      )}
    </div>
  );
}
