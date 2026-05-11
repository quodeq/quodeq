import { useEffect, useRef, useState } from "react";
import { verifyFinding } from "./api";

const VERDICT_STYLES = {
  false_positive: { color: "#0a7", background: "#e8f7ee" },
  confirmed: { color: "#c00", background: "#fde8e8" },
  inconclusive: { color: "#888", background: "#f3f3f3" },
};

// Cap a single verify at 4 min. Longer than the worst observed run (~105s for
// gemma4:26b cold) so we don't kill real work, but bounded so a dropped
// connection (e.g. dev-server auto-reload) doesn't strand the UI in
// "Verifying…" forever.
const VERIFY_TIMEOUT_MS = 240_000;

export default function VerificationDetail({ evaluationId, dimension, findingId }) {
  const [state, setState] = useState({ status: "idle", result: null, error: null });
  const abortRef = useRef(null);

  // If the user clicks away (different finding, different tab) while a verify
  // is in flight, abort it so we don't leak the request.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  async function onVerify() {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const timer = setTimeout(
      () => controller.abort(new DOMException("timeout", "TimeoutError")),
      VERIFY_TIMEOUT_MS,
    );

    setState({ status: "loading", result: null, error: null });
    try {
      const result = await verifyFinding(
        evaluationId,
        dimension,
        findingId,
        { signal: controller.signal },
      );
      setState({ status: "done", result, error: null });
    } catch (err) {
      const message =
        err?.name === "TimeoutError" || err?.cause?.name === "TimeoutError"
          ? `Verification timed out after ${VERIFY_TIMEOUT_MS / 1000}s. The server may have restarted; click Retry.`
          : err?.name === "AbortError"
          ? "Verification cancelled."
          : err?.message || String(err);
      setState({ status: "error", result: null, error: message });
    } finally {
      clearTimeout(timer);
      if (abortRef.current === controller) abortRef.current = null;
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
