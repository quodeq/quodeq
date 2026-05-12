import { useMemo, useState } from "react";

export default function FindingsList({ findings, selectedId, onSelect }) {
  const [query, setQuery] = useState("");
  const [reversed, setReversed] = useState(false);

  const filtered = useMemo(() => {
    if (!findings) return [];
    const q = query.trim().toLowerCase();
    const list = q
      ? findings.filter((f) => {
          const haystack = `${f.title || ""} ${f.file || ""} ${f.dimension || ""}`.toLowerCase();
          return haystack.includes(q);
        })
      : findings;
    return reversed ? [...list].reverse() : list;
  }, [findings, query, reversed]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 1,
          background: "#fff",
          borderBottom: "1px solid #eee",
          padding: "0.5rem",
          display: "flex",
          gap: "0.5rem",
          alignItems: "center",
        }}
      >
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by title or file…"
          style={{
            flex: 1,
            padding: "0.4rem 0.6rem",
            fontSize: "0.9rem",
            border: "1px solid #ccc",
            borderRadius: 4,
          }}
        />
        <button
          type="button"
          onClick={() => setReversed((v) => !v)}
          title={reversed ? "Restore original order" : "Reverse list order"}
          aria-pressed={reversed}
          style={{
            padding: "0.4rem 0.6rem",
            fontSize: "0.85rem",
            border: "1px solid #ccc",
            borderRadius: 4,
            background: reversed ? "#eef" : "#fff",
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          {reversed ? "↑↓ reversed" : "↑↓ reverse"}
        </button>
      </div>
      <div
        style={{
          padding: "0.25rem 0.75rem",
          color: "#666",
          fontSize: "0.8rem",
        }}
      >
        {filtered.length} of {findings?.length || 0}
      </div>
      {filtered.length === 0 ? (
        <div style={{ padding: "1rem", color: "#666" }}>
          {findings && findings.length > 0 ? "No matches." : "No findings."}
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {filtered.map((f) => {
            const id = `${f.dimension}/${f.id}`;
            const isSelected = selectedId === f.id;
            return (
              <li
                key={id}
                onClick={() => onSelect(f.dimension, f.id)}
                style={{
                  padding: "0.5rem 1rem",
                  cursor: "pointer",
                  borderBottom: "1px solid #eee",
                  background: isSelected ? "#f0f4ff" : "transparent",
                }}
              >
                <div style={{ fontSize: "0.85rem", color: "#666" }}>
                  {f.dimension} · {f.severity}
                </div>
                <div style={{ fontWeight: 500 }}>{f.title || f.id}</div>
                <div style={{ fontSize: "0.85rem", color: "#888" }}>
                  {f.file}:{f.line}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
