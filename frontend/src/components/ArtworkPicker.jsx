export default function ArtworkPicker({ artworkUrl, candidates, loading, error, onSelect }) {
  return (
    <div className="artwork-picker">
      <div className="artwork-picker-row">
        <label>Cover art</label>
        {artworkUrl && <img className="artwork-preview" src={artworkUrl} alt="Selected cover art" />}
        {loading && <span className="status">Searching...</span>}
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
