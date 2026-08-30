import { getAiGuessOnline, searchArtwork } from "./api";
import { mergeGuesses } from "./utils";

// Shared by SearchTab (resolving one selected result) and PlaylistTab
// (resolving every item up front): hand the video's title + description to
// the AI to fill anime/type/number/song/artist, then fetch a matching
// cover. `hint` is the search-box parse in SearchTab, null in PlaylistTab.
export async function resolveItemTags(item, hint, aiEnabled) {
  let finalGuess = hint || {};

  if (aiEnabled) {
    try {
      const data = await getAiGuessOnline(item.id, item.title, finalGuess);
      finalGuess = mergeGuesses(finalGuess, data.result);
    } catch {
      // AI unavailable (no LLM_API_KEY, rate limit, network) - fall back to
      // whatever hint we had; the form can be filled in by hand.
    }
  }

  let artworkUrl = null;
  let artworkCandidates = [];
  if (finalGuess.anime) {
    try {
      const artData = await searchArtwork(finalGuess.anime);
      artworkCandidates = artData.results;
      artworkUrl = artData.results[0]?.artwork_url ?? null;
    } catch {
      // No cover art found - the form's own picker can still be used manually.
    }
  }

  return { finalGuess, artworkUrl, artworkCandidates };
}
