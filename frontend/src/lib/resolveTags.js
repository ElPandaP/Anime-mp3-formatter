import { getAiGuessOnline, guessTags, searchArtwork } from "./api";
import { mergeGuesses } from "./utils";

async function fetchArtwork(anime) {
  if (!anime) return { artworkUrl: null, artworkCandidates: [] };
  try {
    const artData = await searchArtwork(anime);
    return {
      artworkUrl: artData.results[0]?.artwork_url ?? null,
      artworkCandidates: artData.results,
    };
  } catch {
    // No cover art found - the form's own picker can still be used manually.
    return { artworkUrl: null, artworkCandidates: [] };
  }
}

// SearchTab: one selected result. Hand title + description to the AI to fill
// anime/type/number/song/artist, then fetch a cover. `hint` is the search-box
// parse.
export async function resolveItemTags(item, hint, aiEnabled) {
  let finalGuess = hint || {};

  if (aiEnabled) {
    try {
      const data = await getAiGuessOnline(item.id, item.title, finalGuess);
      finalGuess = mergeGuesses(finalGuess, data.result);
    } catch (err) {
      // YouTube rate-limit or a gone video are meaningful to the caller
      // (pause the run / skip the track) - re-raise those.
      if (err.status === "rate_limited" || err.status === "unavailable") throw err;
      // Anything else (no LLM_API_KEY, AI rate limit, network) - fall back to
      // whatever hint we had; the form can be filled in by hand.
    }
  }

  return { finalGuess, ...(await fetchArtwork(finalGuess.anime)) };
}

// PlaylistTab prep, priority 2: the audio is already downloaded (stage 1).
// Guess tags off the description the server already has, then fetch a cover.
// No YouTube here - runs several at once.
export async function resolvePreparedTags(item, aiEnabled) {
  let finalGuess = {};
  try {
    const data = await guessTags(item.id, item.title, {}, aiEnabled);
    if (data.result) finalGuess = data.result;
  } catch (err) {
    if (err.status === "rate_limited") throw err;
    // Guess failure - leave tags blank for the user to fill by hand.
  }
  return { finalGuess, ...(await fetchArtwork(finalGuess.anime)) };
}
