import { useState } from "react";
import { verifyFinding } from "./api";

const VERDICT_STYLES = {
  false_positive: { color: "#0a7", background: "#e8f7ee" },
  confirmed: { color: "#c00", background: "#fde8e8" },
  inconclusive: { color: "#888", background: "#f3f3f3" },
};

export default function VerificationDetail({ evaluationId, dimension, findingId }) {
  const [state, setState] = useState({ status: "idle", result: null, error: null });

  async function onVerify() {
    setState({ status: "loading", result: null, error: null });
    try {
      const result = await verifyFinding(evaluationId, dimension, findingId);
      setState({ status: "done", result, error: null });
    } catch (err) {
      setState({ status: "error", result: null, error: err.message });
    }
  }

  return (
    <div>
      <h3>Verification</h3>
      <div style={{ marginBottom: "1rem", color: "#666", fontSize: "0.9rem" }}>
        {dimension} · finding {findingId}
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <button
          onClick={onVerify}
          disabled={state.status === "loading"}
          style={{
            padding: "0.5rem 1rem",
            cursor: state.status === "loading" ? "wait" : "pointer",
          }}
        >
          {state.status === "idle" && "▶ Verify"}
          {state.status === "loading" && "Verifying…"}
          {state.status === "error" && "Retry"}
          {state.status === "done" && "Re-verify"}
        </button>
        {state.status === "loading" && (
          <span style={{ marginLeft: "0.75rem", color: "#666" }}>
            (10–60s)
          </span>
        )}
      </div>

      {state.status === "error" && (
        <div
          style={{
            color: "#c00",
            background: "#fde8e8",
            padding: "0.5rem 1rem",
            borderRadius: 4,
            marginBottom: "1rem",
          }}
        >
          Error: {state.error}
        </div>
      )}

      {state.status === "done" && state.result && (
        <Result result={state.result} />
      )}
    </div>
  );
}

function Result({ result }) {
  const verdictStyle = VERDICT_STYLES[result.verdict] || {};
  return (
    <div>
      <div
        style={{
          ...verdictStyle,
          padding: "0.5rem 1rem",
          borderRadius: 4,
          marginBottom: "1rem",
          fontWeight: 600,
        }}
      >
        Verdict: {result.verdict}
        {typeof result.confidence === "number" && (
          <span style={{ marginLeft: "0.5rem", fontWeight: 400 }}>
            ({Math.round(result.confidence * 100)}%)
          </span>
        )}
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <em>{result.evidence_summary}</em>
      </div>

      <Section title="Checklist">
        <table style={{ width: "100%", fontSize: "0.9rem" }}>
          <tbody>
            {Object.entries(result.checklist || {}).map(([q, a]) => (
              <tr key={q}>
                <td style={{ padding: "0.25rem 0.5rem", color: "#666" }}>{q}</td>
                <td style={{ padding: "0.25rem 0.5rem" }}>{a.answer}</td>
                <td style={{ padding: "0.25rem 0.5rem", color: "#888", fontSize: "0.85rem" }}>
                  {a.cite || ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Extracted facts">
        <FindingsTable findings={result.findings} />
      </Section>

      <Section title="Audit log" collapsible defaultClosed>
        <pre style={{ fontSize: "0.8rem", background: "#fafafa", padding: "0.5rem", overflow: "auto", maxHeight: 200 }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      </Section>

      {result.consistency_warnings?.length > 0 && (
        <Section title="Warnings">
          <ul>
            {result.consistency_warnings.map((w, i) => (
              <li key={i} style={{ color: "#a60" }}>{w}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function FindingsTable({ findings }) {
  if (!findings) return null;
  return (
    <table style={{ width: "100%", fontSize: "0.9rem" }}>
      <tbody>
        {Object.entries(findings).map(([key, f]) => (
          <tr key={key}>
            <td style={{ padding: "0.25rem 0.5rem", color: "#666", width: "12rem" }}>{key}</td>
            <td style={{ padding: "0.25rem 0.5rem" }}>{f.value || "—"}</td>
            <td style={{ padding: "0.25rem 0.5rem", color: "#888", fontSize: "0.85rem" }}>
              {f.cite || ""}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Section({ title, collapsible, defaultClosed, children }) {
  const [open, setOpen] = useState(!defaultClosed);
  return (
    <div style={{ marginBottom: "1rem" }}>
      <h4
        style={{ cursor: collapsible ? "pointer" : "default", margin: "0 0 0.25rem 0" }}
        onClick={collapsible ? () => setOpen(!open) : undefined}
      >
        {collapsible && (open ? "▾" : "▸")} {title}
      </h4>
      {open && children}
    </div>
  );
}
