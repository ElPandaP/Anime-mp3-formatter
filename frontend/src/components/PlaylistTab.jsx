import { useMemo, useRef, useState } from "react";
import { loadPlaylist, downloadTrack, prefetchAudio, normalizeCached } from "../lib/api";
import { runPool, buildPreview, sanitizeFilename } from "../lib/utils";
import { resolvePreparedTags } from "../lib/resolveTags";
import {
  BLANK_TAGS, RATE_LIMIT_TEXT, TUNING_DEFAULTS,
  buildSegments, makeLimiter, sleep,
} from "../lib/playlist";
import PlaylistRow from "./PlaylistRow";
import TagForm from "./TagForm";

// A segment is prepared in three lanes so YouTube isn't the bottleneck:
//   1. fetch     the only lane that hits YouTube - a few at a time with a gap
//   2. tags      AI guess + cover art; a row is editable once this lands
//   3. normalise the loudness pass; runs on in the background while you review
// Concurrency and pacing for each come from config.json (via the `tuning` prop).

export default function PlaylistTab({ outputDir, aiEnabled, tuning }) {
  const t = useMemo(() => ({ ...TUNING_DEFAULTS, ...(tuning || {}) }), [tuning]);

  const [url, setUrl] = useState("");
  const [items, setItems] = useState([]);
  const [segments, setSegments] = useState([]);
  const [activeSeg, setActiveSeg] = useState(null);
  const [segDone, setSegDone] = useState({});
  const [skippedOnLoad, setSkippedOnLoad] = useState(0);
  const [itemData, setItemData] = useState({});
  // Per-item outcome that isn't a normal download result: "skipped" (video
  // gone) set during tag prep.
  const [itemStatus, setItemStatus] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [loadingPlaylist, setLoadingPlaylist] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [preparedCount, setPreparedCount] = useState(0);
  // Audio normalisation still churning in the background after the rows are
  // already up and editable.
  const [finishingAudio, setFinishingAudio] = useState(false);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadedCount, setDownloadedCount] = useState(0);
  const [results, setResults] = useState({});
  const [summary, setSummary] = useState(null);
  const [rateLimited, setRateLimited] = useState(false);
  // Filenames that would collide - shown as a warning; a second click on
  // "Download all" goes ahead anyway.
  const [nameClashes, setNameClashes] = useState([]);

  // Set true the moment a rate-limit is seen, so both pools stop pulling new
  // work instead of grinding through the rest and failing every one.
  const stopRef = useRef(false);

  const segItems = useMemo(() => {
    if (activeSeg === null || !segments[activeSeg]) return [];
    const { start, end } = segments[activeSeg];
    return items.slice(start, end);
  }, [items, segments, activeSeg]);

  const downloadableItems = useMemo(
    () => segItems.filter((it) => itemStatus[it.id] !== "skipped"),
    [segItems, itemStatus],
  );

  function resetRunState() {
    setResults({});
    setSummary(null);
    setNameClashes([]);
    setRateLimited(false);
    stopRef.current = false;
  }

  async function handleLoad() {
    if (!url.trim()) return;
    setLoadingPlaylist(true);
    setError(null);
    setItems([]);
    setSegments([]);
    setActiveSeg(null);
    setSegDone({});
    setSkippedOnLoad(0);
    setItemData({});
    setItemStatus({});
    setEditingId(null);
    resetRunState();
    try {
      const data = await loadPlaylist(url);
      setItems(data.items);
      setSkippedOnLoad(data.skipped_unavailable || 0);
      const segs = buildSegments(data.items.length, t.segment_size);
      setSegments(segs);
      setLoadingPlaylist(false);
      // Short lists: no chunking, jump straight in like before.
      if (segs.length === 1) enterSegment(0, data.items, segs);
    } catch (err) {
      setError(
        err.status === "rate_limited" ? RATE_LIMIT_TEXT : err.message,
      );
      setLoadingPlaylist(false);
    }
  }

  function enterSegment(index, itemList = items, segList = segments) {
    setActiveSeg(index);
    resetRunState();
    const { start, end } = segList[index];
    prepareSegment(itemList.slice(start, end));
  }

  async function prepareSegment(slice) {
    setPreparing(true);
    setPreparedCount(slice.filter((it) => itemData[it.id] || itemStatus[it.id] === "skipped").length);

    const runTags = makeLimiter(t.tags_concurrency);
    const runNormalize = makeLimiter(t.normalize_concurrency);
    const tagJobs = [];
    const normJobs = [];

    const finishBlank = (id) => {
      setItemData((prev) => ({ ...prev, [id]: { ...BLANK_TAGS } }));
      setPreparedCount((c) => c + 1);
    };

    // Lane 1: fetch each track's audio from YouTube, a few at a time with a
    // short gap. The moment one lands, kick off the tag guess (lane 2) and the
    // normalise (lane 3) and move straight on to the next fetch.
    await runPool(
      slice,
      t.fetch_concurrency,
      async (item, index) => {
        // Idempotent: a retry re-runs the whole slice but skips anything
        // already resolved or already marked gone.
        if (itemData[item.id] || itemStatus[item.id] === "skipped") return;
        if (index > 0) await sleep(t.prep_gap_ms);
        if (stopRef.current) return;

        try {
          await prefetchAudio(item.id, item.title);
        } catch (err) {
          if (err.status === "rate_limited") {
            stopRef.current = true;
            setRateLimited(true);
            return;
          }
          if (err.status === "unavailable") {
            setItemStatus((prev) => ({ ...prev, [item.id]: "skipped" }));
            setPreparedCount((c) => c + 1);
            return;
          }
          finishBlank(item.id); // no audio - user can still fill tags by hand
          return;
        }

        tagJobs.push(
          runTags(async () => {
            try {
              const { finalGuess, artworkUrl, artworkCandidates } = await resolvePreparedTags(
                item,
                aiEnabled,
              );
              setItemData((prev) => ({
                ...prev,
                [item.id]: {
                  anime: finalGuess.anime || "",
                  type: finalGuess.type || "OP",
                  number: finalGuess.number || "",
                  song: finalGuess.song || "",
                  artist: finalGuess.artist || "",
                  artworkUrl,
                  artworkCandidates,
                },
              }));
              setPreparedCount((c) => c + 1);
            } catch (err) {
              if (err.status === "rate_limited") {
                stopRef.current = true;
                setRateLimited(true);
              } else {
                finishBlank(item.id);
              }
            }
          }),
        );

        normJobs.push(
          runNormalize(() => normalizeCached(item.id).catch(() => {})),
        );
      },
      () => stopRef.current,
    );

    // Rows are ready once fetch + tags are done - normalisation can finish on
    // its own while the user reviews them.
    await Promise.allSettled(tagJobs);
    setPreparing(false);

    if (normJobs.length) {
      setFinishingAudio(true);
      Promise.allSettled(normJobs).then(() => setFinishingAudio(false));
    }
  }

  function handleSaveEdit(values) {
    setItemData((prev) => ({ ...prev, [editingId]: values }));
    setEditingId(null);
    setNameClashes([]);
  }

  function findNameClashes() {
    const byName = {};
    for (const item of downloadableItems) {
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
    setRateLimited(false);
    stopRef.current = false;
    await runDownload();
  }

  async function runDownload() {
    setDownloading(true);
    setSummary(null);
    setDownloadedCount(
      downloadableItems.filter((it) => results[it.id]?.status === "ok").length,
    );

    const resultsAcc = { ...results };
    await runPool(
      downloadableItems,
      t.download_concurrency,
      async (item) => {
        if (resultsAcc[item.id]?.status === "ok") return;
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
          resultsAcc[item.id] = { id: item.id, status: "ok", path: res.path };
        } catch (err) {
          const status =
            err.status === "rate_limited"
              ? "rate_limited"
              : err.status === "unavailable"
                ? "unavailable"
                : "error";
          resultsAcc[item.id] = { id: item.id, status, error: err.message };
          if (status === "rate_limited") {
            stopRef.current = true;
            setRateLimited(true);
          }
        }
        setResults((prev) => ({ ...prev, [item.id]: resultsAcc[item.id] }));
        setDownloadedCount((c) => c + 1);
      },
      () => stopRef.current,
    );

    setDownloading(false);

    const ok = downloadableItems.filter((it) => resultsAcc[it.id]?.status === "ok").length;
    const unavailable =
      segItems.filter((it) => itemStatus[it.id] === "skipped").length +
      downloadableItems.filter((it) => resultsAcc[it.id]?.status === "unavailable").length;
    const stalled = downloadableItems.filter(
      (it) => !resultsAcc[it.id] || resultsAcc[it.id].status === "rate_limited",
    ).length;

    const parts = [`${ok} OK`];
    if (unavailable) parts.push(`${unavailable} skipped`);
    if (stalled) parts.push(`${stalled} rate-limited`);
    setSummary(`Segment ${activeSeg + 1}/${segments.length}: ${parts.join(" · ")}`);

    if (!stalled) {
      setSegDone((prev) => ({ ...prev, [activeSeg]: unavailable ? "partial" : "done" }));
    }
  }

  async function handleRetry() {
    stopRef.current = false;
    setRateLimited(false);
    const needPrep = segItems.filter(
      (it) => !itemData[it.id] && itemStatus[it.id] !== "skipped",
    );
    if (needPrep.length) {
      await prepareSegment(segItems);
    } else {
      await runDownload();
    }
  }

  function rowStatus(item) {
    if (itemStatus[item.id] === "skipped") {
      return { kind: "unavailable", text: "Skipped — video unavailable" };
    }
    const r = results[item.id];
    if (!r) return null;
    if (r.status === "ok") return { kind: "ok", text: "OK" };
    if (r.status === "unavailable") return { kind: "unavailable", text: "Skipped — video unavailable" };
    if (r.status === "rate_limited") return { kind: "rate_limited", text: "Rate-limited — retry later" };
    return { kind: "error", text: r.error };
  }

  function markUnavailable(id) {
    setItemStatus((prev) => (prev[id] === "skipped" ? prev : { ...prev, [id]: "skipped" }));
  }

  const editingItem = editingId ? items.find((item) => item.id === editingId) : null;
  const showPicker = activeSeg === null && segments.length > 1;
  const busy = loadingPlaylist || preparing || downloading;

  return (
    <div>
      <div className="row">
        <input
          type="text"
          placeholder="YouTube playlist URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button onClick={handleLoad} disabled={busy}>
          {loadingPlaylist ? "Loading..." : "Load playlist"}
        </button>
      </div>
      {error && <span className="status error">{error}</span>}
      {skippedOnLoad > 0 && (
        <span className="status">
          {skippedOnLoad} track{skippedOnLoad > 1 ? "s" : ""} skipped (private or deleted).
        </span>
      )}

      {showPicker && (
        <div className="segments">
          <p>
            This playlist has {items.length} tracks. Process it in chunks of {t.segment_size} to
            stay under YouTube's rate limit — pick one to start:
          </p>
          <div className="row">
            {segments.map((seg, i) => (
              <button key={i} onClick={() => enterSegment(i)} disabled={busy}>
                {seg.start + 1}–{seg.end}
                {segDone[i] === "done" ? " ✓" : segDone[i] === "partial" ? " ◐" : ""}
              </button>
            ))}
          </div>
        </div>
      )}

      {rateLimited && (
        <div className="status error name-clashes">
          <p>{RATE_LIMIT_TEXT}</p>
          <button onClick={handleRetry} disabled={busy}>
            Retry remaining
          </button>
        </div>
      )}

      {activeSeg !== null && segItems.length > 0 && (
        <>
          {preparing && (
            <div className="prepare-status">
              <span className="spinner-large" />
              <p>
                Fetching &amp; tagging: {preparedCount}/{segItems.length}...
              </p>
            </div>
          )}

          <div className="row playlist-actions">
            {segments.length > 1 && (
              <button onClick={() => setActiveSeg(null)} disabled={busy}>
                ← Chunks
              </button>
            )}
            <button
              onClick={handleDownloadAll}
              disabled={preparing || downloading || !downloadableItems.length}
            >
              {downloading
                ? `Downloading ${downloadedCount}/${downloadableItems.length}...`
                : nameClashes.length
                  ? "Download anyway"
                  : `Download all (${downloadableItems.length})`}
            </button>
            {finishingAudio && !preparing && !downloading && (
              <span className="status">finishing audio in background…</span>
            )}
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
            {segItems.map((item) => (
              <PlaylistRow
                key={item.id}
                video={item}
                data={itemData[item.id]}
                status={rowStatus(item)}
                onEdit={() => setEditingId(item.id)}
                onUnavailable={() => markUnavailable(item.id)}
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
