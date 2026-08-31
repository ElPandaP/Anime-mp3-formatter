// Helpers for the playlist tab. See PlaylistTab.jsx for how prep is staged.

export const BLANK_TAGS = { anime: "", type: "OP", number: "", song: "", artist: "" };

export const RATE_LIMIT_TEXT =
  "YouTube is rate-limiting requests (anti-bot check). It clears on its own in " +
  "a few minutes - wait, then hit Retry.";

// Values from GET /api/settings; these only apply until that response lands.
export const TUNING_DEFAULTS = {
  fetch_concurrency: 2,
  prep_gap_ms: 800,
  tags_concurrency: 3,
  normalize_concurrency: 2,
  download_concurrency: 2,
  segment_size: 50,
};

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// A concurrency gate for work that arrives over time (runPool needs the whole
// list up front; here lane 1 feeds jobs in as each fetch finishes).
export function makeLimiter(max) {
  let active = 0;
  const queue = [];
  const pump = () => {
    if (active >= max || !queue.length) return;
    active++;
    const { fn, resolve, reject } = queue.shift();
    Promise.resolve().then(fn).then(resolve, reject).finally(() => {
      active--;
      pump();
    });
  };
  return (fn) =>
    new Promise((resolve, reject) => {
      queue.push({ fn, resolve, reject });
      pump();
    });
}

// Split a playlist into chunks the user works through one at a time, so a
// single sitting never hammers YouTube hard enough to get blocked.
export function buildSegments(count, size) {
  const segments = [];
  for (let start = 0; start < count; start += size) {
    segments.push({ start, end: Math.min(start + size, count) });
  }
  return segments.length ? segments : [{ start: 0, end: 0 }];
}
