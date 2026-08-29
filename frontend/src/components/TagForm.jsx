import { useMemo, useState } from "react";
import { useTagFields } from "../hooks/useTagFields";
import { downloadTrack } from "../api";
import { mergeGuesses } from "../utils";
import ArtworkPicker from "./ArtworkPicker";

export default function TagForm({ video, outputDir, queryGuess, aiGuess, initialArtwork, onSave }) {
  const guess = useMemo(
    () => mergeGuesses(queryGuess, aiGuess),
    [queryGuess, aiGuess]
  );
  const f = useTagFields(guess, initialArtwork);
  const [status, setStatus] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const isEditMode = typeof onSave === "function";

  async function handleSubmit(e) {
    e.preventDefault();

    if (isEditMode) {
      onSave({
        anime: f.anime,
        type: f.type,
        number: f.number,
        song: f.song,
        artist: f.artist,
        artworkUrl: f.artworkUrl,
        artworkCandidates: f.artworkCandidates,
      });
      return;
    }

    setDownloading(true);
    setStatus(null);
    try {
      const data = await downloadTrack({
        id: video.id,
        anime: f.anime,
        type: f.type,
        number: f.number,
        song: f.song,
        artist: f.artist,
        artwork_url: f.artworkUrl,
        output_dir: outputDir,
      });
      setStatus({ ok: true, text: `Saved to ${data.path}` });
    } catch (err) {
      setStatus({ ok: false, text: err.message });
    } finally {
      setDownloading(false);
    }
  }

  return (
    <form className="tag-form" onSubmit={handleSubmit}>
      <div className="field-row">
        <label>Anime</label>
        <input value={f.anime} onChange={(e) => f.setAnime(e.target.value)} required />
      </div>
      <div className="field-row">
        <label>Type</label>
        <select value={f.type} onChange={(e) => f.setType(e.target.value)}>
          <option value="OP">OP</option>
          <option value="ED">ED</option>
          <option value="OST">OST</option>
        </select>
        <input className="f-numero" value={f.number} onChange={(e) => f.setNumber(e.target.value)} placeholder="No." />
      </div>
      <div className="field-row">
        <label>Song</label>
        <input value={f.song} onChange={(e) => f.setSong(e.target.value)} required />
      </div>
      <div className="field-row">
        <label>Artist</label>
        <input value={f.artist} onChange={(e) => f.setArtist(e.target.value)} required />
      </div>
      <div className="field-row preview-row">
        <span className="preview-label">Will be saved as:</span>
        <span className="preview-text">{f.preview}</span>
      </div>
      <ArtworkPicker
        artworkUrl={f.artworkUrl}
        candidates={f.artworkCandidates}
        loading={f.artworkLoading}
        error={f.artworkError}
        onSelect={f.setArtworkUrl}
      />
      <button type="submit" className="download-btn" disabled={downloading}>
        {isEditMode ? "Done" : downloading ? "Downloading..." : "Download"}
      </button>
      {status && <span className={`status ${status.ok ? "ok" : "error"}`}>{status.text}</span>}
    </form>
  );
}
