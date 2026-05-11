export default function FindingsList({ findings, selectedId, onSelect }) {
  if (!findings || findings.length === 0) {
    return <div style={{ padding: "1rem", color: "#666" }}>No findings.</div>;
  }
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {findings.map((f) => {
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
  );
}
