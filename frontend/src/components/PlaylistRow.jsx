import { useAudioPreview } from "../hooks/useAudioPreview";
import { formatDuration, buildPreview } from "../lib/utils";
import PreviewThumb from "./PreviewThumb";

export default function PlaylistRow({ video, data, status, onEdit, onUnavailable }) {
  const preview = useAudioPreview(video.id, onUnavailable);
  const summary = data ? buildPreview(data.anime, data.type, data.number, data.song) : "";
  const unavailable = status?.kind === "unavailable";

  return (
    <div className="playlist-row">
      <div className="playlist-row-top">
        <PreviewThumb
          thumbnail={data?.artworkUrl || video.thumbnail}
          loading={preview.loading}
          isPlaying={preview.isPlaying}
          onClick={preview.toggle}
          disabled={unavailable}
        />
        <div className="fields">
          <div className="video-title">
            {video.title} ({formatDuration(video.duration)})
          </div>
          <div className="row-preview">
            {data ? summary || "(no tags)" : unavailable ? "" : "preparing…"}
          </div>
          {data?.artist && <div className="row-artist">{data.artist}</div>}
          {status && (
            <span
              className={`row-status status ${
                status.kind === "ok" ? "ok" : status.kind === "error" ? "error" : ""
              }`}
            >
              {status.text}
            </span>
          )}
        </div>
        <button type="button" onClick={onEdit} disabled={!data || unavailable}>
          Edit
        </button>
      </div>
      {!unavailable && preview.error && <span className="status error">{preview.error}</span>}
      {preview.url && (
        <audio ref={preview.audioRef} src={preview.url} controls autoPlay className="preview-bar" />
      )}
    </div>
  );
}
