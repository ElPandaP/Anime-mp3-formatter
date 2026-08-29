const VOLUME_KEY = "anime-mp3-preview-volume";
const audios = new Set();

export function getDefaultVolume() {
  const stored = localStorage.getItem(VOLUME_KEY);
  const v = stored !== null ? parseFloat(stored) : 1;
  return Number.isNaN(v) ? 1 : Math.min(1, Math.max(0, v));
}

export function setDefaultVolume(v) {
  localStorage.setItem(VOLUME_KEY, String(v));
}

export function registerAudio(audioEl) {
  audios.add(audioEl);
  const onPlay = () => {
    audios.forEach((a) => {
      if (a !== audioEl) a.pause();
    });
  };
  audioEl.addEventListener("play", onPlay);
  return () => {
    audioEl.removeEventListener("play", onPlay);
    audios.delete(audioEl);
  };
}
