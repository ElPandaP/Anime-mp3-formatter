import { useEffect, useRef, useState } from "react";
import { getStreamUrl } from "../lib/api";
import { registerAudio, getDefaultVolume } from "../lib/previewPlayer";

export function useAudioPreview(id, onUnavailable) {
  const [url, setUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef(null);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return undefined;
    el.volume = getDefaultVolume();
    const unregister = registerAudio(el);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onPause);
    return () => {
      unregister();
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onPause);
    };
  }, [url]);

  async function toggle() {
    if (url) {
      const el = audioRef.current;
      if (!el) return;
      if (el.paused) el.play();
      else el.pause();
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getStreamUrl(id);
      setUrl(data.url);
    } catch (err) {
      // The video is gone (private / deleted / copyright-blocked). Reuse this
      // failed request - which happened anyway - to flag the row upstream.
      if (err.status === "unavailable") {
        setError("Video unavailable");
        onUnavailable?.();
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }

  return { url, loading, error, isPlaying, toggle, audioRef };
}
