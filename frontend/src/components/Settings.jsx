import { useEffect, useRef, useState } from "react";
import { getSettings, saveSettings, browseFolder } from "../lib/api";

export default function Settings({ outputDir, setOutputDir }) {
  const [status, setStatus] = useState(null);
  const [browsing, setBrowsing] = useState(false);
  const lastSaved = useRef("");

  useEffect(() => {
    getSettings().then((data) => {
      setOutputDir(data.output_dir || "");
      lastSaved.current = data.output_dir || "";
    });
  }, [setOutputDir]);

  async function saveIfChanged(value) {
    if (!value.trim() || value === lastSaved.current) return;
    setStatus("Saving...");
    try {
      const data = await saveSettings(value);
      setOutputDir(data.output_dir);
      lastSaved.current = data.output_dir;
      setStatus("Saved");
    } catch (err) {
      setStatus(err.message);
    }
  }

  async function handleBrowse() {
    setBrowsing(true);
    setStatus(null);
    try {
      const data = await browseFolder(outputDir);
      if (data.path) {
        setOutputDir(data.path);
        await saveIfChanged(data.path);
      }
    } catch (err) {
      setStatus(err.message);
    } finally {
      setBrowsing(false);
    }
  }

  return (
    <section className="settings">
      <label htmlFor="output-dir">Destination folder</label>
      <div className="row">
        <input
          id="output-dir"
          type="text"
          value={outputDir}
          onChange={(e) => setOutputDir(e.target.value)}
          onBlur={(e) => saveIfChanged(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && e.target.blur()}
          placeholder="C:\Users\...\Music\AnimeMp3"
        />
        <button onClick={handleBrowse} disabled={browsing}>
          {browsing ? "..." : "Browse"}
        </button>
        {status && <span className="status">{status}</span>}
      </div>
    </section>
  );
}
