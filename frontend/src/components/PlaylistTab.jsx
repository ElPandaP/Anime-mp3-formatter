import { useState } from "react";
import { loadPlaylist, downloadTrack } from "../lib/api";
import { runPool, buildPreview, sanitizeFilename } from "../lib/utils";
import { resolveItemTags } from "../lib/resolveTags";
import PlaylistRow from "./PlaylistRow";
import TagForm from "./TagForm";

// Tag prep is network/LLM-bound - several can run at once. Downloads are
// CPU-bound (ffmpeg mp3 conversion + loudness pass), so keep those lower.
const TAG_CONCURRENCY = 5;
const DOWNLOAD_CONCURRENCY = 3;

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
  const [downloadedCount, setDownloadedCount] = useState(0);
  const [results, setResults] = useState({});
  const [summary, setSummary] = useState(null);
  // Filenames that would collide - shown as a warning; a second click on
  // "Download all" goes ahead anyway.
  const [nameClashes, setNameClashes] = useState([]);

  async function handleLoad() {
    if (!url.trim()) return;
    setLoadingPlaylist(true);
    setError(null);
    setSummary(null);
    setResults({});
    setItems([]);
    setItemData({});
    setEditingId(null);
    setNameClashes([]);
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

    await runPool(playlistItems, TAG_CONCURRENCY, async (item) => {
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
    });

    setPreparing(false);
  }

  function handleSaveEdit(values) {
    setItemData((prev) => ({ ...prev, [editingId]: values }));
    setEditingId(null);
    setNameClashes([]);
  }

  function findNameClashes() {
    const byName = {};
    for (const item of items) {
      const d = itemData[item.id] || {};
      const name = sanitizeFilename(buildPreview(d.anime, d.type, d.number, d.song));
      (byName[name] ||= []).push(d.song || item.title);
    }
    return Object.entries(byName)
      .filter(([, songs]) => songs.length > 1)
      .map(([name, songs]) => ({ name, songs }));
  }

  async function handleDownloadAll() {
    const clashes = findNameClashes();
    if (clashes.length && !nameClashes.length) {
      // First click with clashes: warn and wait for a second click.
      setNameClashes(clashes);
      return;
    }
    setNameClashes([]);
    setDownloading(true);
    setSummary(null);
    setResults({});
    setDownloadedCount(0);

    const resultsAcc = {};
    await runPool(items, DOWNLOAD_CONCURRENCY, async (item) => {
      const data = itemData[item.id] || {};
      try {
        const res = await downloadTrack({
          id: item.id,
          anime: data.anime || "",
          type: data.type || "OP",
          number: data.number || "",
          song: data.song || "",
          artist: data.artist || "",
          artwork_url: data.artworkUrl || null,
          output_dir: outputDir,
        });
        resultsAcc[item.id] = { id: item.id, success: true, path: res.path };
      } catch (err) {
        resultsAcc[item.id] = { id: item.id, success: false, error: err.message };
      }
      setResults((prev) => ({ ...prev, [item.id]: resultsAcc[item.id] }));
      setDownloadedCount((c) => c + 1);
    });

    const ok = Object.values(resultsAcc).filter((r) => r.success).length;
    setSummary(`Done: ${ok}/${items.length} downloaded successfully.`);
    setDownloading(false);
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
              {downloading
                ? `Downloading ${downloadedCount}/${items.length}...`
                : nameClashes.length
                  ? "Download anyway"
                  : "Download all"}
            </button>
          </div>

          {nameClashes.length > 0 && !downloading && (
            <div className="status error name-clashes">
              <p>
                These tracks would be saved to the same filename and overwrite each
                other. Edit their tags, or click "Download anyway" to continue.
              </p>
              <ul>
                {nameClashes.map((clash) => (
                  <li key={clash.name}>
                    <strong>{clash.name}.mp3</strong> — {clash.songs.join(", ")}
                  </li>
                ))}
              </ul>
            </div>
          )}

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
