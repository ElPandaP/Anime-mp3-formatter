async function request(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || "Network error");
    // "rate_limited" (YouTube anti-bot / 429) or "unavailable" (private /
    // deleted / copyright-blocked video); callers branch on this.
    err.status = data.status || null;
    err.httpStatus = res.status;
    throw err;
  }
  return data;
}

export const getSettings = () => request("/api/settings");

export const saveSettings = (output_dir) =>
  request("/api/settings", { method: "POST", body: JSON.stringify({ output_dir }) });

export const browseFolder = (initial) =>
  request("/api/browse-folder", { method: "POST", body: JSON.stringify({ initial }) });

export const searchVideos = (query) =>
  request("/api/search", { method: "POST", body: JSON.stringify({ query }) });

export const getAiGuessOnline = (id, title, guess) =>
  request("/api/ai-guess-online", { method: "POST", body: JSON.stringify({ id, title, guess }) });

// Playlist prep, stage 1 - the only YouTube hit per track. Run one at a time
// with a gap between calls.
export const prefetchAudio = (id, title) =>
  request("/api/prefetch-audio", { method: "POST", body: JSON.stringify({ id, title }) });

// Playlist prep, priority 2 - no network: guess tags off the description
// stage 1 fetched. A row is ready to show/edit once this returns.
export const guessTags = (id, title, guess, ai) =>
  request("/api/guess-tags", { method: "POST", body: JSON.stringify({ id, title, guess, ai }) });

// Playlist prep, priority 3 - no network: loudness-normalise a stage-1 file.
// Background work; only has to finish before that track is downloaded.
export const normalizeCached = (id) =>
  request("/api/normalize-cached", { method: "POST", body: JSON.stringify({ id }) });

export const getStreamUrl = (id) =>
  request("/api/stream", { method: "POST", body: JSON.stringify({ id }) });

export const loadPlaylist = (url) =>
  request("/api/playlist", { method: "POST", body: JSON.stringify({ url }) });

export const searchArtwork = (query) =>
  request("/api/artwork", { method: "POST", body: JSON.stringify({ query }) });

export const downloadTrack = (payload) =>
  request("/api/download", { method: "POST", body: JSON.stringify(payload) });
