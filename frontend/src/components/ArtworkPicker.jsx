export default function ArtworkPicker({
  artworkUrl,
  candidates,
  loading,
  error,
  onSearch,
  onSelect,
}) {
  return (
    <div className="artwork-picker">
      <div className="artwork-picker-row">
        <label>Cover art</label>
        <button type="button" onClick={onSearch} disabled={loading}>
          {loading ? "Searching..." : "Search cover art"}
        </button>
        {artworkUrl && <img className="artwork-preview" src={artworkUrl} alt="Selected cover art" />}
      </div>
      {error && <span className="status error">{error}</span>}
      {candidates.length > 0 && (
        <div className="artwork-candidates">
          {candidates.map((c, i) => (
            <div
              key={i}
              className={`candidate ${c.artwork_url === artworkUrl ? "selected" : ""}`}
              onClick={() => onSelect(c.artwork_url)}
            >
              <img src={c.artwork_url} alt="" />
              <span className="cand-label">
                {c.artist} - {c.collection || c.track}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
