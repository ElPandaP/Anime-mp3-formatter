import { useState } from "react";
import Settings from "./components/Settings";
import SearchTab from "./components/SearchTab";
import PlaylistTab from "./components/PlaylistTab";
import VolumeControl from "./components/VolumeControl";

export default function App() {
  const [tab, setTab] = useState("search");
  const [outputDir, setOutputDir] = useState("");

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
        <VolumeControl />
      </nav>

      {tab === "search" ? <SearchTab outputDir={outputDir} /> : <PlaylistTab outputDir={outputDir} />}
    </div>
  );
}
