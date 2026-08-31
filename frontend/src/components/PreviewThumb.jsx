import { useState } from "react";

export default function PreviewThumb({ thumbnail, loading, isPlaying, onClick, disabled }) {
  // Remember the exact src that failed, so a later thumbnail (artwork loading
  // in) is tried again without needing an effect to reset a flag.
  const [brokenSrc, setBrokenSrc] = useState(null);
  const showImage = thumbnail && brokenSrc !== thumbnail && !disabled;

  return (
    <div
      className={`thumb-wrap${disabled ? " thumb-disabled" : ""}`}
      onClick={disabled ? undefined : onClick}
      title={
        disabled ? "Video unavailable" : isPlaying ? "Pause preview" : "Play preview"
      }
    >
      {showImage ? (
        <img src={thumbnail} alt="" onError={() => setBrokenSrc(thumbnail)} />
      ) : (
        <div className="thumb-placeholder" />
      )}
      <span className="play-overlay">
        {disabled ? "✕" : loading ? "…" : isPlaying ? "⏸" : "▶"}
      </span>
    </div>
  );
}
