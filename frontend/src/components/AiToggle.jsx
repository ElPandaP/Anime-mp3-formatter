export default function AiToggle({ enabled, available, onToggle }) {
  return (
    <label className="ai-toggle" title={available ? "" : "No LLM_API_KEY configured in .env"}>
      <span>AI{available ? "" : " (not configured)"}</span>
      <span className={`switch ${enabled ? "on" : ""} ${!available ? "disabled" : ""}`}>
        <input type="checkbox" checked={enabled} onChange={onToggle} disabled={!available} />
        <span className="switch-track">
          <span className="switch-thumb" />
        </span>
      </span>
    </label>
  );
}
