export default function PreviewThumb({ thumbnail, loading, isPlaying, onClick }) {
  return (
    <div className="thumb-wrap" onClick={onClick} title={isPlaying ? "Pause preview" : "Play preview"}>
      <img src={thumbnail} alt="" />
      <span className="play-overlay">{loading ? "…" : isPlaying ? "⏸" : "▶"}</span>
    </div>
  );
}
