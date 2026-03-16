import { memo, useState } from 'react';
import { PLAN_TEST_INSTRUCTION_GROUP, PLAN_TEST_INSTRUCTION_SINGLE } from '../../../utils/explorerUtils.js';

const SEVERITY_ORDER = ['critical', 'major', 'minor', 'unknown'];

function parseFileRef(rawFile, rawLine) {
  if (!rawFile) return { filePath: null, line: rawLine ?? null };
  const m = rawFile.match(/^(.*?)(?::(\d+))?$/);
  const filePath = m[1] || rawFile;
  const line = rawLine ?? (m[2] ? parseInt(m[2], 10) : null);
  return { filePath, line };
}

function CopyIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2"/>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  );
}

function buildPrinciplePlanText(principle) {
  const totalViolations = principle.total || 0;
  const lines = [
    'You are a senior software engineer performing a targeted code review.',
    'Apply minimal, surgical fixes — no refactoring, no style changes beyond what is required.',
    '',
    `# Fix Plan: ${principle.principle}`,
    '',
    `**Total violations:** ${totalViolations}`,
    '',
    '---',
    '',
  ];

  SEVERITY_ORDER.forEach((sev) => {
    const vs = (principle.violations || []).filter(
      (v) => (v.severity || 'minor').toLowerCase() === sev
    );
    if (vs.length === 0) return;
    lines.push(`## ${sev.charAt(0).toUpperCase() + sev.slice(1)} violations (${vs.length})`);
    lines.push('');
    vs.forEach((v, i) => {
      const loc = v.file ? `${v.file}${v.line ? `:${v.line}` : ''}` : '';
      lines.push(`### ${i + 1}.${loc ? ` \`${loc}\`` : ''}`);
      if (v.reason) lines.push('', `**Why it's a violation:** ${v.reason}`);
      if (v.snippet) {
        lines.push('', '**Affected code:**');
        lines.push('```');
        v.snippet.split('\n').forEach((l) => lines.push(l));
        lines.push('```');
      }
      lines.push('');
    });
  });

  lines.push('---');
  lines.push('');
  lines.push('For each violation above, provide a concrete, step-by-step fix.');
  lines.push('Return each fix as an exact replacement block or unified diff. No explanations beyond what is needed to apply the fix.');
  lines.push(PLAN_TEST_INSTRUCTION_GROUP);
  return lines.join('\n').trim();
}

function buildViolationPlanText(v, principleName) {
  const title = principleName || 'Violation';
  const loc = v.file ? `${v.file}${v.line ? `:${v.line}` : ''}` : '';
  const lines = [
    `# Fix Request: ${title}`,
    '',
    `**Severity:** ${v.severity || 'unknown'}`,
  ];
  if (loc) lines.push(`**File:** ${loc}`);
  if (v.snippet) lines.push('', '## Affected Code', '```', v.snippet, '```');
  if (v.reason) lines.push('', "## Why It's a Violation", v.reason);
  lines.push('', '---', 'Please provide a concrete, step-by-step fix for this specific violation.');
  if (loc) lines.push(`Apply it to \`${loc}\`.`);
  lines.push(PLAN_TEST_INSTRUCTION_SINGLE);
  return lines.join('\n').trim();
}

function CopyButton({ onClick, label }) {
  const [copied, setCopied] = useState(false);
  const handleClick = () => {
    onClick();
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button className="detail-copy-btn" onClick={handleClick}>
      {copied ? 'Copied!' : label}
      <CopyIcon />
    </button>
  );
}

function FileCopyBtn({ display, copyText }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="vlive-detail-file-btn"
      onClick={() => {
        navigator.clipboard.writeText(copyText);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? 'Copied!' : display}
      <CopyIcon />
    </button>
  );
}

function ViolationCard({ v, principleName, index }) {
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const ref = line != null ? `${filePath}:${line}` : filePath;
  const display = line != null ? `${filename}:${line}` : filename;
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`} style={{ animationDelay: `${Math.min(index * 30, 300)}ms` }}>
      <div className="vdetail-row-main">
        <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
        <span className="vrow-label">[{principleName}]</span>
        {filename && (
          <FileCopyBtn display={display} copyText={ref} />
        )}
        <CopyButton
          label="Fix plan"
          onClick={() => navigator.clipboard.writeText(buildViolationPlanText(v, principleName))}
        />
      </div>
      <div className="vlive-detail">
        {(v.title || v.reason) && (
          <div className="vlive-detail-section">
            <div className="vlive-detail-section-header">
              {v.title && <span className="vlive-detail-section-label">Reason</span>}
              {v.reqRefs?.filter(r => r.url)?.length > 0 &&
                <span className="cwe-link-group">{v.reqRefs.filter(r => r.url).map((ref, i) => (
                  <a key={i} className="cwe-link" href={ref.url} target="_blank" rel="noopener noreferrer">{ref.label}</a>
                ))}</span>
              }
            </div>
            {v.title && <p className="vlive-detail-title">{v.title}</p>}
            {v.reason && <>
              <span className="vlive-detail-section-label">Detail</span>
              <p className="vlive-detail-reason">{v.reason}</p>
            </>}
          </div>
        )}
        {v.snippet && <pre className="vlive-snippet">{v.snippet.replace(/\\n/g, '\n')}</pre>}
      </div>
    </div>
  );
}

const PrincipleDetailPage = memo(function PrincipleDetailPage({ principle }) {
  const totalViolations = principle.total || 0;

  const violationsBySeverity = SEVERITY_ORDER.reduce((acc, sev) => {
    acc[sev] = (principle.violations || []).filter(
      (v) => (v.severity || 'minor').toLowerCase() === sev
    );
    return acc;
  }, {});

  return (
    <>
      <div className="section-header">
        <h3 className="section-title file-detail-title">{principle.principle}</h3>
      </div>
      <section className="panel file-detail-summary-panel">
        <div className="file-detail-stats-row">
          <div className="file-detail-stats">
            <span className="file-detail-stat">
              <strong>{totalViolations}</strong> violations
            </span>
            {principle.critical > 0 && (
              <>
                <span className="file-detail-stat-sep">·</span>
                <span className="file-detail-stat severity-tag critical">{principle.critical} critical</span>
              </>
            )}
            {principle.major > 0 && (
              <>
                <span className="file-detail-stat-sep">·</span>
                <span className="file-detail-stat severity-tag major">{principle.major} major</span>
              </>
            )}
            {principle.minor > 0 && (
              <>
                <span className="file-detail-stat-sep">·</span>
                <span className="file-detail-stat severity-tag minor">{principle.minor} minor</span>
              </>
            )}
          </div>
          <CopyButton
            label="Principle fix plan"
            onClick={() => navigator.clipboard.writeText(buildPrinciplePlanText(principle))}
          />
        </div>
      </section>

      {SEVERITY_ORDER.map((sev) => {
        const violations = violationsBySeverity[sev];
        if (!violations || violations.length === 0) return null;
        return (
          <div key={sev}>
            <div className="violation-group-header">
              <span className="violation-group-title">{sev.charAt(0).toUpperCase() + sev.slice(1)}</span>
              <span className="violation-group-count">{violations.length}</span>
            </div>
            <div className="vlive-violations-group">
              {violations.map((v, idx) => (
                <ViolationCard key={idx} v={v} principleName={principle.principle} index={idx} />
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
});

export default PrincipleDetailPage;
