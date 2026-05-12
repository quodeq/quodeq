import { useState } from "react";
import FindingsList from "./verifier/FindingsList";
import VerificationDetail from "./verifier/VerificationDetail";

export default function Verifier({ evaluationId, findings }) {
  const [selected, setSelected] = useState(null);

  return (
    <div className="verifier-tab" style={{ display: "flex", height: "100%", minHeight: 0 }}>
      {/* Left column: long list of findings, scrolls independently. */}
      <div
        style={{
          flex: "0 0 40%",
          borderRight: "1px solid #ddd",
          overflowY: "auto",
          minHeight: 0,
        }}
      >
        <FindingsList
          findings={findings}
          selectedId={selected?.findingId}
          onSelect={(dim, fid) => setSelected({ dimension: dim, findingId: fid })}
        />
      </div>
      {/* Right column: verification detail. Always visible — no independent
          scroll. Long-content subsections (audit log) cap themselves. */}
      <div style={{ flex: "1 1 60%", padding: "1rem", overflow: "visible" }}>
        {selected ? (
          <VerificationDetail
            evaluationId={evaluationId}
            dimension={selected.dimension}
            findingId={selected.findingId}
          />
        ) : (
          <div style={{ color: "#666", padding: "2rem" }}>
            Select a finding from the list to verify it.
          </div>
        )}
      </div>
    </div>
  );
}
