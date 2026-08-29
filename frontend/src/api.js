async function request(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Network error");
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

export const getStreamUrl = (id) =>
  request("/api/stream", { method: "POST", body: JSON.stringify({ id }) });

export const loadPlaylist = (url) =>
  request("/api/playlist", { method: "POST", body: JSON.stringify({ url }) });

export const searchArtwork = (query) =>
  request("/api/artwork", { method: "POST", body: JSON.stringify({ query }) });

export const downloadTrack = (payload) =>
  request("/api/download", { method: "POST", body: JSON.stringify(payload) });

export const downloadPlaylist = (items, output_dir) =>
  request("/api/playlist/download", { method: "POST", body: JSON.stringify({ items, output_dir }) });
