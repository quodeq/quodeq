/**
 * TopFindings — tabular summary of the highest-severity findings across all
 * dimensions, rendered in the terminal design system. Matches the
 * `TOP_FINDINGS` block from the Overview mockup.
 *
 * Columns:  SEV  DIM  PRINCIPLE  FILE:LINE  CWE  TITLE
 *
 * Input: the accumulated `dimensions` array (same shape the dashboard already
 * ships to the Overview panel). Every violation is flat-mapped with its
 * dimension name, sorted newest-severity-first, and the top `limit` rows are
 * rendered. No extra API call is required.
 */
import { useMemo } from 'react';
import { SEVERITY_ORDER, parseFileRef } from '../../../utils/formatters.js';
import { GridTable, GridRow, GridCell, SectionLabel, SevBadge } from '../../../components/terminal/index.js';

const DEFAULT_LIMIT = 6;
const CWE_RE = /CWE-\d+/i;

function extractCwe(violation) {
  const refs = violation?.reqRefs || [];
  for (const r of refs) {
    const fromLabel = (r?.label || '').match(CWE_RE);
    if (fromLabel) return fromLabel[0].toUpperCase();
    const fromUrl = (r?.url || '').match(CWE_RE);
    if (fromUrl) return fromUrl[0].toUpperCase();
  }
  return '';
}

function sevRank(sev) {
  const i = SEVERITY_ORDER.indexOf((sev || 'unknown').toLowerCase());
  return i === -1 ? SEVERITY_ORDER.length : i;
}

/**
 * Flatten every dimension's violations into a single array, tagging each one
 * with its parent dimension's name so the DIM column can render it.
 */
function collectFindings(dimensions) {
  const out = [];
  if (!Array.isArray(dimensions)) return out;
  for (const dim of dimensions) {
    const dimName = dim?.dimension || '';
    const vs = dim?.violations || [];
    for (const v of vs) {
      out.push({ ...v, _dim: dimName });
    }
  }
  return out;
}

function formatFileLine(violation) {
  const { filePath, line } = parseFileRef(violation?.file, violation?.line);
  if (!filePath) return '';
  // Show just the basename to match the mockup (e.g. `_webview_window.py:79`
  // instead of the full `src/quodeq/dashboard/_webview_window.py:79`). The
  // full path stays available on the row's click-through handler.
  const basename = filePath.split('/').pop() || filePath;
  return line != null ? `${basename}:${line}` : basename;
}

function formatTitle(violation) {
  // The data model uses `title` for the short reason headline
  // (e.g. "Hardcoded credential in fallback path") and `reason` for the
  // long paragraph explanation. The TITLE column wants the brief one.
  return violation?.title || violation?.reason || '—';
}

function shortDim(name) {
  const lower = String(name || '').toLowerCase();
  // "maintainability" → "maintain." to save horizontal space; others pass through
  if (lower === 'maintainability') return 'maintain.';
  return lower;
}

/**
 * @param {object} props
 * @param {Array}  props.dimensions        Accumulated dimensions array.
 * @param {number} [props.limit=6]         Max rows to render.
 * @param {(v: object) => void} [props.onFindingClick]
 */
export default function TopFindings({ dimensions, limit = DEFAULT_LIMIT, onFindingClick }) {
  const findings = useMemo(
    () => collectFindings(dimensions)
      .sort((a, b) => sevRank(a.severity) - sevRank(b.severity))
      .slice(0, limit),
    [dimensions, limit],
  );

  if (findings.length === 0) return null;

  const critical = findings.filter((f) => (f.severity || '').toLowerCase() === 'critical').length;
  const major    = findings.filter((f) => (f.severity || '').toLowerCase() === 'major').length;

  return (
    <section className="top-findings" aria-label="Top findings">
      <div className="top-findings__head">
        <SectionLabel>top_findings</SectionLabel>
        <span className="top-findings__meta">
          {critical} CRITICAL · {major} MAJOR · SORTED BY SEVERITY
        </span>
      </div>

      <GridTable columns="72px 120px 150px 1fr 100px 2fr" dense>
        <GridRow header>
          <GridCell>SEV</GridCell>
          <GridCell>DIM</GridCell>
          <GridCell>PRINCIPLE</GridCell>
          <GridCell>FILE:LINE</GridCell>
          <GridCell>CWE</GridCell>
          <GridCell>TITLE</GridCell>
        </GridRow>

        {findings.map((f, i) => {
          const sev = (f.severity || 'minor').toLowerCase();
          const fileLine = formatFileLine(f);
          const cwe = extractCwe(f);
          return (
            <GridRow key={`${f.file || 'nofile'}-${f.line ?? 'noline'}-${i}`} onClick={onFindingClick ? () => onFindingClick(f) : undefined}>
              <GridCell><SevBadge level={sev} /></GridCell>
              <GridCell muted>{shortDim(f._dim)}</GridCell>
              <GridCell muted>{String(f.principle || '—').toLowerCase()}</GridCell>
              <GridCell muted>{fileLine || '—'}</GridCell>
              <GridCell><span className="top-findings__cwe">{cwe || '—'}</span></GridCell>
              <GridCell>{formatTitle(f)}</GridCell>
            </GridRow>
          );
        })}
      </GridTable>
    </section>
  );
}
