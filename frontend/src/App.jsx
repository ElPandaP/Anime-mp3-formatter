import { useEffect, useState } from "react";
import Settings from "./components/Settings";
import SearchTab from "./components/SearchTab";
import PlaylistTab from "./components/PlaylistTab";
import VolumeControl from "./components/VolumeControl";
import AiToggle from "./components/AiToggle";
import { getSettings } from "./api";

const AI_ENABLED_KEY = "ai-guess-enabled";

export default function App() {
  const [tab, setTab] = useState("search");
  const [outputDir, setOutputDir] = useState("");
  const [aiAvailable, setAiAvailable] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(false);

  useEffect(() => {
    getSettings().then((data) => {
      const available = !!data.ai_available;
      setAiAvailable(available);
      const stored = localStorage.getItem(AI_ENABLED_KEY);
      setAiEnabled(stored !== null ? stored === "true" : available);
    });
  }, []);

  function toggleAi() {
    setAiEnabled((prev) => {
      const next = !prev;
      localStorage.setItem(AI_ENABLED_KEY, String(next));
      return next;
    });
  }

  return (
    <div className="app">
      <header>
        <h1>Anime MP3 Formatter</h1>
        <p className="subtitle">
          Download OPs, EDs and OSTs from YouTube, tagged and ready to use as local files in Spotify
        </p>
      </header>

      <Settings outputDir={outputDir} setOutputDir={setOutputDir} />

      <nav className="tabs">
        <div className="tab-buttons">
          <button className={`tab-btn ${tab === "search" ? "active" : ""}`} onClick={() => setTab("search")}>
            Search song
          </button>
          <button className={`tab-btn ${tab === "playlist" ? "active" : ""}`} onClick={() => setTab("playlist")}>
            YouTube playlist
          </button>
        </div>
        <div className="nav-controls">
          <AiToggle enabled={aiEnabled} available={aiAvailable} onToggle={toggleAi} />
          <VolumeControl />
        </div>
      </nav>

      {tab === "search" ? (
        <SearchTab outputDir={outputDir} aiEnabled={aiEnabled} />
      ) : (
        <PlaylistTab outputDir={outputDir} aiEnabled={aiEnabled} />
      )}
    </div>
  );
}
