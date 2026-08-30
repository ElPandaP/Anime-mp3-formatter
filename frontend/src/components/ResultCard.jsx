import { useAudioPreview } from "../hooks/useAudioPreview";
import { formatDuration } from "../lib/utils";
import PreviewThumb from "./PreviewThumb";

export default function ResultCard({ item, onSelect }) {
  const preview = useAudioPreview(item.id);

  return (
    <div className="result-card">
      <div className="result-card-top">
        <PreviewThumb
          thumbnail={item.thumbnail}
          loading={preview.loading}
          isPlaying={preview.isPlaying}
          onClick={preview.toggle}
        />
        <div className="result-info">
          <div className="title">{item.title}</div>
          <div className="meta">
            {item.channel} · {formatDuration(item.duration)}
          </div>
        </div>
        <button onClick={() => onSelect(item)}>Select</button>
      </div>
      {preview.error && <span className="status error">{preview.error}</span>}
      {preview.url && (
        <audio ref={preview.audioRef} src={preview.url} controls autoPlay className="preview-bar" />
      )}
    </div>
  );
}
