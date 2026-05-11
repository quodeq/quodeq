import { useState } from "react";
import FindingsList from "./verifier/FindingsList";
import VerificationDetail from "./verifier/VerificationDetail";

export default function Verifier({ evaluationId, findings }) {
  const [selected, setSelected] = useState(null);

  return (
    <div className="verifier-tab" style={{ display: "flex", height: "100%" }}>
      <div style={{ flex: "0 0 40%", borderRight: "1px solid #ddd", overflow: "auto" }}>
        <FindingsList
          findings={findings}
          selectedId={selected?.findingId}
          onSelect={(dim, fid) => setSelected({ dimension: dim, findingId: fid })}
        />
      </div>
      <div style={{ flex: "1 1 60%", overflow: "auto", padding: "1rem" }}>
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
