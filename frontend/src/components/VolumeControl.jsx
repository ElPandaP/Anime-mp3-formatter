import { useState } from "react";
import { getDefaultVolume, setDefaultVolume } from "../previewPlayer";

export default function VolumeControl() {
  const [volume, setVolume] = useState(getDefaultVolume());

  function handleChange(e) {
    const v = parseFloat(e.target.value);
    setVolume(v);
    setDefaultVolume(v);
  }

  const icon = volume === 0 ? "🔇" : volume < 0.5 ? "🔉" : "🔊";

  return (
    <div className="volume-control" title="Default preview volume">
      <span className="volume-icon">{icon}</span>
      <input type="range" min="0" max="1" step="0.01" value={volume} onChange={handleChange} />
    </div>
  );
}
