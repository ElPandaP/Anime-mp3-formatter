import { useAudioPreview } from "../hooks/useAudioPreview";
import { formatDuration, buildPreview } from "../utils";
import PreviewThumb from "./PreviewThumb";

export default function PlaylistRow({ video, data, status, onEdit }) {
  const preview = useAudioPreview(video.id);
  const summary = data ? buildPreview(data.anime, data.type, data.number, data.song) : "";

  return (
    <div className="playlist-row">
      <div className="playlist-row-top">
        <PreviewThumb
          thumbnail={data?.artworkUrl || video.thumbnail}
          loading={preview.loading}
          isPlaying={preview.isPlaying}
          onClick={preview.toggle}
        />
        <div className="fields">
          <div className="video-title">
            {video.title} ({formatDuration(video.duration)})
          </div>
          <div className="row-preview">{summary || "(no tags yet)"}</div>
          {data?.artist && <div className="row-artist">{data.artist}</div>}
          {status && <span className={`row-status status ${status.ok ? "ok" : "error"}`}>{status.text}</span>}
        </div>
        <button type="button" onClick={onEdit}>
          Edit
        </button>
      </div>
      {preview.error && <span className="status error">{preview.error}</span>}
      {preview.url && (
        <audio ref={preview.audioRef} src={preview.url} controls autoPlay className="preview-bar" />
      )}
    </div>
  );
}
