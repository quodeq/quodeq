import { memo, useState } from 'react';
import { PLAN_TEST_INSTRUCTION_GROUP, PLAN_TEST_INSTRUCTION_SINGLE } from '../../../utils/explorerUtils.js';
import { SEVERITY_ORDER, parseFileRef } from '../../../utils/formatters.js';
import CopyButton, { CopyIcon } from '../../../components/CopyButton.jsx';

const COPY_FEEDBACK_MS = 1500;

function buildFilePlanText(file) {
  const totalViolations = SEVERITY_ORDER.reduce(
    (sum, sev) => sum + (file.violationsBySeverity?.[sev]?.length || 0),
    0
  );
  const lines = [
    'You are a senior software engineer performing a targeted code review.',
    'Apply minimal, surgical fixes — no refactoring, no style changes beyond what is required.',
    '',
    `# Fix Plan: \`${file.file}\``,
    '',
    `**Total violations:** ${totalViolations}`,
    '',
    '---',
    '',
  ];

  SEVERITY_ORDER.forEach((sev) => {
    const vs = file.violationsBySeverity?.[sev] || [];
    if (vs.length === 0) return;
    lines.push(`## ${sev.charAt(0).toUpperCase() + sev.slice(1)} violations (${vs.length})`);
    lines.push('');
    vs.forEach((v, i) => {
      const loc = v.file ? `${v.file}${v.line ? `:${v.line}` : ''}` : '';
      lines.push(`### ${i + 1}. ${v.principle || 'Violation'}${loc ? ` — \`${loc}\`` : ''}`);
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

function buildViolationPlanText(v) {
  const title = [v.dimension, v.principle].filter(Boolean).join(' / ') || 'Violation';
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

function FileCopyBtn({ display, copyText }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="vlive-detail-file-btn"
      onClick={() => {
        navigator.clipboard.writeText(copyText);
        setCopied(true);
        setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
      }}
    >
      {copied ? 'Copied!' : display}
      <CopyIcon />
    </button>
  );
}

function ViolationCard({ v, index }) {
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const ref = line != null ? `${filePath}:${line}` : filePath;
  const display = line != null ? `${filename}:${line}` : filename;
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`} style={{ animationDelay: `${Math.min(index * 30, 300)}ms` }}>
      <div className="vdetail-row-main">
        <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
        {v.dimension && <span className="vrow-label">[{v.dimension}]</span>}
        {v.principle && <span className="vrow-label">[{v.principle}]</span>}
        {filename && (
          <FileCopyBtn display={display} copyText={ref} />
        )}
        <CopyButton
          label="Fix plan"
          onClick={() => navigator.clipboard.writeText(buildViolationPlanText(v))}
        />
      </div>
      <div className="vlive-detail">
        {(v.title || v.reason) && (
          <div className="vlive-detail-section">
            <div className="vlive-detail-section-header">
              <span className="vlive-detail-section-label">Reason</span>
              {v.reqRefs?.filter(r => r.url && /^https?:\/\//.test(r.url))?.length > 0 &&
                <span className="cwe-link-group">{v.reqRefs.filter(r => r.url && /^https?:\/\//.test(r.url)).map((ref, i) => (
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

const FileDetailPage = memo(function FileDetailPage({ file }) {
  const totalViolations = file.total || 0;
  const dimensionsCount = file.dimensionsCount || 0;

  return (
    <>
      <section className="panel file-detail-summary-panel">
        <h3 className="file-detail-title">{file.file}</h3>
        <div className="file-detail-stats-row">
          <div className="file-detail-stats">
            {file.critical > 0 && (
              <span className="file-detail-stat severity-tag critical">{file.critical} critical</span>
            )}
            {file.major > 0 && (
              <span className="file-detail-stat severity-tag major">{file.major} major</span>
            )}
            {file.minor > 0 && (
              <span className="file-detail-stat severity-tag minor">{file.minor} minor</span>
            )}
            {(file.critical > 0 || file.major > 0 || file.minor > 0) && <span className="file-detail-stat-sep">·</span>}
            <span className="file-detail-stat">
              <strong>{totalViolations}</strong> violations
            </span>
            <span className="file-detail-stat-sep">·</span>
            <span className="file-detail-stat">
              <strong>{dimensionsCount}</strong> {dimensionsCount === 1 ? 'dimension' : 'dimensions'}
            </span>
          </div>
          <CopyButton
            label="File fix plan"
            onClick={() => navigator.clipboard.writeText(buildFilePlanText(file))}
          />
        </div>
      </section>

      {SEVERITY_ORDER.map((sev) => {
        const violations = file.violationsBySeverity?.[sev] || [];
        if (violations.length === 0) return null;
        return (
          <div key={sev}>
            <div className="violation-group-header">
              <span className="violation-group-title">{sev.charAt(0).toUpperCase() + sev.slice(1)}</span>
              <span className="violation-group-count">{violations.length}</span>
            </div>
            <div className="vlive-violations-group">
              {violations.map((v, idx) => (
                <ViolationCard key={idx} v={v} index={idx} />
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
});

export default FileDetailPage;
