export function formatDuration(sec) {
  if (sec === null || sec === undefined) return "";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

// Mirrors backend title_parsing.sanitize_filename - strips the characters
// Windows/most filesystems reject, collapses whitespace. Used to spot two
// tracks that would land on the same .mp3 path before downloading.
export function sanitizeFilename(name) {
  const cleaned = (name || "")
    .replace(/[<>:"/\\|?*]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned || "untitled";
}

export function buildPreview(anime, type, number, song) {
  anime = (anime || "").trim();
  type = (type || "").trim();
  number = (number || "").trim();
  song = (song || "").trim();

  let label;
  if (type.toUpperCase() === "OST") {
    label = `${anime} OST`.trim();
  } else if (number) {
    label = `${anime} ${type} ${number}`.trim();
  } else {
    label = `${anime} ${type}`.trim();
  }
  label = label.replace(/\s+/g, " ").trim();
  return song ? (label ? `${label} - ${song}` : song) : label;
}

const TYPE_WORDS = {
  opening: "OP",
  op: "OP",
  ending: "ED",
  ed: "ED",
  soundtrack: "OST",
  ost: "OST",
};
const TYPE_ALT = Object.keys(TYPE_WORDS).join("|");

function titleCase(s) {
  return s
    .trim()
    .split(/\s+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function parseAnimeQuery(query) {
  const q = (query || "").trim();
  const empty = { anime: "", type: "OP", number: "" };
  if (!q) return empty;

  const prefixRe = new RegExp(`^(${TYPE_ALT})\\.?\\s*(\\d+)?\\s+(.+)$`, "i");
  const suffixRe = new RegExp(`^(.+?)\\s+(${TYPE_ALT})\\.?\\s*(\\d+)?$`, "i");

  let m = q.match(prefixRe);
  if (m) {
    return { type: TYPE_WORDS[m[1].toLowerCase()], number: m[2] || "", anime: titleCase(m[3]) };
  }
  m = q.match(suffixRe);
  if (m) {
    return { anime: titleCase(m[1]), type: TYPE_WORDS[m[2].toLowerCase()], number: m[3] || "" };
  }
  return empty;
}

// Runs `worker(item, index)` across all items with at most `concurrency`
// running at once. Resolves when every item is done. The worker is
// responsible for its own error handling - the pool never aborts early on a
// thrown error, so one failed item doesn't stop the rest.
// `shouldStop` is an optional predicate checked before each item is picked
// up; once it returns true the pool drains without starting anything new
// (used to bail out of a segment the moment YouTube rate-limits us).
export async function runPool(items, concurrency, worker, shouldStop) {
  const queue = [...items.entries()];
  const drain = async () => {
    while (queue.length) {
      if (shouldStop && shouldStop()) return;
      const [index, item] = queue.shift();
      await worker(item, index);
    }
  };
  const workers = Array.from({ length: Math.min(concurrency, items.length) }, drain);
  await Promise.all(workers);
}

// Merges guess objects in priority order: later, truthy fields win over
// earlier ones. Lets a weak baseline (title heuristics) be topped up by
// better sources (search-query parsing, AI) without losing fields the
// better source didn't determine.
export function mergeGuesses(...guesses) {
  const result = {};
  for (const guess of guesses) {
    if (!guess) continue;
    for (const key of ["anime", "type", "number", "song", "artist"]) {
      if (guess[key]) result[key] = guess[key];
    }
  }
  return result;
}
