import { memo, useState } from 'react';
import { PLAN_TEST_INSTRUCTION_GROUP, PLAN_TEST_INSTRUCTION_SINGLE } from '../../../utils/explorerUtils.js';

const EVAL_SEVERITY_ORDER = ['critical', 'major', 'minor', 'unknown'];

const GRADE_TIERS = {
  exemplary: 'grade-top',
  good: 'grade-high',
  proficient: 'grade-high',
  adequate: 'grade-mid',
  developing: 'grade-mid',
  poor: 'grade-low',
  insufficient: 'grade-low',
  critical: 'grade-bottom',
  a: 'grade-top',
  b: 'grade-high',
  c: 'grade-mid',
  d: 'grade-low',
  f: 'grade-bottom',
};

function gradeColorClass(grade) {
  if (!grade) return 'grade-none';
  const lower = grade.trim().toLowerCase();
  if (GRADE_TIERS[lower]) return GRADE_TIERS[lower];
  const first = lower.charAt(0);
  return GRADE_TIERS[first] || 'grade-none';
}

function CopyIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2"/>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  );
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

function parseFileRef(rawFile, rawLine) {
  if (!rawFile) return { filePath: null, line: rawLine ?? null };
  const m = rawFile.match(/^(.*?)(?::(\d+))?$/);
  const filePath = m[1] || rawFile;
  const line = rawLine ?? (m[2] ? parseInt(m[2], 10) : null);
  return { filePath, line };
}

const PAGE_SIZE = 20;

const EvalPrincipleDetailPage = memo(function EvalPrincipleDetailPage({ evalPrincipal }) {
  const {
    principleData,
    principle,
    score,
    grade,
    dimViolations = [],
    dimCompliance = [],
  } = evalPrincipal;

  const [showAllCompliance, setShowAllCompliance] = useState(false);

  const violations = (principleData?.violations?.length > 0)
    ? principleData.violations
    : dimViolations;

  const compliance = dimCompliance.filter((c) => c.file || c.reason || c.snippet);

  const violationsBySeverity = EVAL_SEVERITY_ORDER.reduce((acc, sev) => {
    acc[sev] = violations.filter((v) => (v.severity || 'minor').toLowerCase() === sev);
    return acc;
  }, {});

  const displayedCompliance = showAllCompliance ? compliance : compliance.slice(0, PAGE_SIZE);
  const hasMoreCompliance = compliance.length > PAGE_SIZE;

  const buildPrinciplePlanText = () => {
    const totalViolations = violations.length;
    const lines = [
      'You are a senior software engineer performing a targeted code review.',
      'Apply minimal, surgical fixes — no refactoring, no style changes beyond what is required.',
      '',
      `# Fix Plan: ${principle}`,
      '',
      `**Total violations:** ${totalViolations}`,
    ];
    if (principleData?.findings) lines.push('', `**Context:** ${principleData.findings}`);
    lines.push('', '---', '');

    EVAL_SEVERITY_ORDER.forEach((sev) => {
      const vs = violationsBySeverity[sev];
      if (!vs || vs.length === 0) return;
      lines.push(`## ${sev.charAt(0).toUpperCase() + sev.slice(1)} violations (${vs.length})`);
      lines.push('');
      vs.forEach((v, i) => {
        const loc = v.file ? `${v.file}${v.line ? `:${v.line}` : ''}` : '';
        lines.push(`### ${i + 1}.${loc ? ` \`${loc}\`` : ''}`);
        const reason = v.reason || v.findings;
        if (reason) lines.push('', `**Why it's a violation:** ${reason}`);
        const code = v.code || v.snippet;
        if (code) {
          lines.push('', '**Affected code:**');
          lines.push('```');
          code.split('\n').forEach((l) => lines.push(l));
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
  };

  const buildViolationPlanText = (v) => {
    const loc = v.file ? `${v.file}${v.line ? `:${v.line}` : ''}` : '';
    const lines = [
      `# Fix Request: ${principle}`,
      '',
      `**Severity:** ${v.severity || 'unknown'}`,
    ];
    if (loc) lines.push(`**File:** ${loc}`);
    const code = v.code || v.snippet;
    if (code) lines.push('', '## Affected Code', '```', code, '```');
    const reason = v.reason || v.findings;
    if (reason) lines.push('', "## Why It's a Violation", reason);
    lines.push('', '---', 'Please provide a concrete, step-by-step fix for this specific violation.');
    if (loc) lines.push(`Apply it to \`${loc}\`.`);
    lines.push(PLAN_TEST_INSTRUCTION_SINGLE);
    return lines.join('\n').trim();
  };

  return (
    <>
      <section className="panel file-detail-summary-panel">
        <h3 className="file-detail-title">{principle}</h3>
        <div className="file-detail-stats-row">
          <div className="file-detail-stats">
            {score && (
              <>
                <span className="file-detail-stat"><strong>{score}</strong></span>
                <span className="file-detail-stat-sep">·</span>
              </>
            )}
            <span className={`chip small ${gradeColorClass(grade)}`}>{grade || '—'}</span>
            {violations.length > 0 && (
              <>
                <span className="file-detail-stat-sep">·</span>
                <span className="file-detail-stat"><strong>{violations.length}</strong> violations</span>
              </>
            )}
            {compliance.length > 0 && (
              <>
                <span className="file-detail-stat-sep">·</span>
                <span className="file-detail-stat"><strong>{compliance.length}</strong> compliant</span>
              </>
            )}
          </div>
          {violations.length > 0 && (
            <CopyButton
              label="Principle fix plan"
              onClick={() => navigator.clipboard.writeText(buildPrinciplePlanText())}
            />
          )}
        </div>
      </section>

      {principleData?.findings && (
        <p className="violation-context-desc" style={{ padding: '0 4px', marginBottom: '4px' }}>
          {principleData.findings}
        </p>
      )}
      {principleData?.justification && (
        <p className="violation-context-desc muted" style={{ padding: '0 4px', marginBottom: '12px' }}>
          {principleData.justification}
        </p>
      )}

      {EVAL_SEVERITY_ORDER.map((sev) => {
        const vs = violationsBySeverity[sev];
        if (!vs || vs.length === 0) return null;
        return (
          <div key={sev}>
            <div className="violation-group-header">
              <span className="violation-group-title">{sev.charAt(0).toUpperCase() + sev.slice(1)}</span>
              <span className="violation-group-count">{vs.length}</span>
            </div>
            <div className="vlive-violations-group">
              {vs.map((v, idx) => (
                <div key={idx} className={`vdetail-row vdetail-row--${v.severity}`} style={{ animationDelay: `${Math.min(idx * 30, 300)}ms` }}>
                  {(() => {
                    const { filePath, line } = parseFileRef(v.file, v.line);
                    const filename = filePath ? filePath.split('/').pop() : null;

                    const ref = line != null ? `${filePath}:${line}` : filePath;
                    const display = line != null ? `${filename}:${line}` : filename;
                    return (
                      <>
                        <div className="vdetail-row-main">
                          <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
                          <span className="vrow-label">[{v.principle || principle}]</span>
                          {filename && (
                            <FileCopyBtn display={display} copyText={ref} />
                          )}
                          <CopyButton
                            label="Fix plan"
                            onClick={() => navigator.clipboard.writeText(buildViolationPlanText(v))}
                          />
                        </div>
                        <div className="vlive-detail">
                          {(v.title || v.reason || v.findings) && (
                            <div className="vlive-detail-section">
                              <div className="vlive-detail-section-header">
                                <span className="vlive-detail-section-label">Reason</span>
                                {v.cwe && <a className="cwe-link" href={`https://cwe.mitre.org/data/definitions/${v.cwe}.html`} target="_blank" rel="noopener noreferrer">CWE-{v.cwe}</a>}
                              </div>
                              {v.title && <p className="vlive-detail-title">{v.title}</p>}
                              {(v.reason || v.findings) && <>
                                <span className="vlive-detail-section-label">Detail</span>
                                <p className="vlive-detail-reason">{v.reason || v.findings}</p>
                              </>}
                            </div>
                          )}
                          {(v.code || v.snippet) && (
                            <pre className="vlive-snippet">{v.code || v.snippet}</pre>
                          )}
                        </div>
                      </>
                    );
                  })()}
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {compliance.length > 0 && (
        <div>
          <div className="violation-group-header">
            <span className="violation-group-title">Compliance</span>
            <span className="violation-group-count">{compliance.length}</span>
          </div>
          <div className="vlive-violations-group">
            {displayedCompliance.map((c, idx) => (
              <div key={idx} className="vdetail-row vdetail-row--compliant" style={{ animationDelay: `${Math.min(idx * 30, 300)}ms` }}>
                {(() => {
                  const { filePath, line } = parseFileRef(c.file, c.line);
                  const filename = filePath ? filePath.split('/').pop() : null;
                  const ref = line != null ? `${filePath}:${line}` : filePath;
                  const display = line != null ? `${filename}:${line}` : filename;
                  return (
                    <>
                      <div className="vdetail-row-main">
                        <span className="vrow-label">[{c.principle || principle}]</span>
                        {filename && (
                          <FileCopyBtn display={display} copyText={ref} />
                        )}
                      </div>
                      <div className="vlive-detail">
                        {(c.title || c.reason) && (
                          <div className="vlive-detail-section">
                            <div className="vlive-detail-section-header">
                              <span className="vlive-detail-section-label">Reason</span>
                              {c.cwe && <a className="cwe-link" href={`https://cwe.mitre.org/data/definitions/${c.cwe}.html`} target="_blank" rel="noopener noreferrer">CWE-{c.cwe}</a>}
                            </div>
                            {c.title && <p className="vlive-detail-title">{c.title}</p>}
                            {c.reason && <>
                              <span className="vlive-detail-section-label">Detail</span>
                              <p className="vlive-detail-reason">{c.reason}</p>
                            </>}
                          </div>
                        )}
                        {(c.code || c.snippet) && (
                          <pre className="vlive-snippet">{c.code || c.snippet}</pre>
                        )}
                      </div>
                    </>
                  );
                })()}
              </div>
            ))}
          </div>
          {hasMoreCompliance && (
            <button
              className="offending-show-more"
              onClick={() => setShowAllCompliance((v) => !v)}
            >
              {showAllCompliance ? 'Show less' : `Show all ${compliance.length} compliance items`}
            </button>
          )}
        </div>
      )}
    </>
  );
});

export default EvalPrincipleDetailPage;
