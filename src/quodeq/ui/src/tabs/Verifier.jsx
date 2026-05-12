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
      {/* Right column: verification detail. Sticky-anchored to the top of
          the flex container so it remains visible while the left column
          scrolls AND while the outer page scrolls. Capped at the viewport
          height with its own scroll fallback for the rare case where the
          full audit log is expanded. */}
      <div
        style={{
          flex: "1 1 60%",
          padding: "1rem",
          position: "sticky",
          top: 0,
          alignSelf: "flex-start",
          maxHeight: "100vh",
          overflowY: "auto",
        }}
      >
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
