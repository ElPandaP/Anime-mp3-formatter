import { forwardRef, useImperativeHandle, useState } from "react";
import { useTagFields } from "../hooks/useTagFields";
import { useAudioPreview } from "../hooks/useAudioPreview";
import { formatDuration, buildPreview } from "../utils";
import ArtworkPicker from "./ArtworkPicker";
import PreviewThumb from "./PreviewThumb";

const PlaylistRow = forwardRef(function PlaylistRow({ video }, ref) {
  const f = useTagFields(video.guess);
  const preview = useAudioPreview(video.id);
  const [status, setStatus] = useState(null);

  useImperativeHandle(ref, () => ({
    getData: () => ({
      id: video.id,
      anime: f.anime,
      type: f.type,
      number: f.number,
      song: f.song,
      artist: f.artist,
      artwork_url: f.artworkUrl,
    }),
    setAnime: f.setAnime,
    setResult: (result) => {
      if (result.success) setStatus({ ok: true, text: "OK" });
      else setStatus({ ok: false, text: result.error });
    },
  }));

  return (
    <div className="playlist-row">
      <div className="playlist-row-top">
        <PreviewThumb
          thumbnail={video.thumbnail}
          loading={preview.loading}
          isPlaying={preview.isPlaying}
          onClick={preview.toggle}
        />
        <div className="fields">
          <div className="video-title">
            {video.title} ({formatDuration(video.duration)})
          </div>
          <input placeholder="Anime" value={f.anime} onChange={(e) => f.setAnime(e.target.value)} />
          <select value={f.type} onChange={(e) => f.setType(e.target.value)}>
            <option value="OP">OP</option>
            <option value="ED">ED</option>
            <option value="OST">OST</option>
          </select>
          <input className="f-numero" placeholder="No." value={f.number} onChange={(e) => f.setNumber(e.target.value)} />
          <input className="f-cancion" placeholder="Song" value={f.song} onChange={(e) => f.setSong(e.target.value)} />
          <input className="f-artista" placeholder="Artist" value={f.artist} onChange={(e) => f.setArtist(e.target.value)} />
          {status && <span className={`row-status status ${status.ok ? "ok" : "error"}`}>{status.text}</span>}
          <div className="row-preview">{buildPreview(f.anime, f.type, f.number, f.song)}</div>
        </div>
      </div>
      {preview.error && <span className="status error">{preview.error}</span>}
      {preview.url && (
        <audio ref={preview.audioRef} src={preview.url} controls autoPlay className="preview-bar" />
      )}
      <ArtworkPicker
        artworkUrl={f.artworkUrl}
        candidates={f.artworkCandidates}
        loading={f.artworkLoading}
        error={f.artworkError}
        onSearch={f.findArtwork}
        onSelect={f.setArtworkUrl}
      />
    </div>
  );
});

export default PlaylistRow;
