import { memo } from 'react';
import { PLAN_TEST_INSTRUCTION_GROUP, PLAN_TEST_INSTRUCTION_SINGLE } from '../../../utils/explorerUtils.js';
import { SEVERITY_ORDER, parseFileRef } from '../../../utils/formatters.js';
import CopyButton from '../../../components/CopyButton.jsx';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';

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

const ANIM_DELAY_PER_ITEM_MS = 30;
const ANIM_MAX_DELAY_MS = 300;

function ViolationCard({ v, principleName, index }) {
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const ref = line != null ? `${filePath}:${line}` : filePath;
  const display = line != null ? `${filename}:${line}` : filename;
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`} style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}>
      <div className="vdetail-row-main">
        <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
        <span className="vrow-label">[{principleName}]</span>
        {filename && (
          <FileCopyBtn display={display} copyText={ref} />
        )}
        <CopyButton
          label="Fix plan"
          onClick={() => copyToClipboard(buildViolationPlanText(v, principleName))}
        />
      </div>
      <div className="vlive-detail">
        {(v.title || v.reason) && (
          <div className="vlive-detail-section">
            <div className="vlive-detail-section-header">
              {v.title && <span className="vlive-detail-section-label">Reason</span>}
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

const PrincipleDetailPage = memo(function PrincipleDetailPage({ principle }) {
  const totalViolations = principle.total || 0;
  const totalCompliance = principle.compliance?.length || 0;

  const violationsBySeverity = {};
  for (const sev of SEVERITY_ORDER) violationsBySeverity[sev] = [];
  for (const v of (principle.violations || [])) {
    const sev = (v.severity || 'minor').toLowerCase();
    if (violationsBySeverity[sev]) violationsBySeverity[sev].push(v);
    else violationsBySeverity['minor'].push(v);
  }

  return (
    <>
      <div className="section-header">
        <h3 className="section-title file-detail-title">{principle.principle}</h3>
      </div>
      <section className="panel file-detail-summary-panel">
        <div className="file-detail-stats-row">
          <div className="file-detail-stats">
            {principle.critical > 0 && (
              <span className="file-detail-stat severity-tag critical">{principle.critical} critical</span>
            )}
            {principle.major > 0 && (
              <span className="file-detail-stat severity-tag major">{principle.major} major</span>
            )}
            {principle.minor > 0 && (
              <span className="file-detail-stat severity-tag minor">{principle.minor} minor</span>
            )}
            {(principle.critical > 0 || principle.major > 0 || principle.minor > 0) && <span className="file-detail-stat-sep">·</span>}
            <span className="file-detail-stat">
              <strong>{totalViolations}</strong> violations
            </span>
            {totalCompliance > 0 && (
              <>
                <span className="file-detail-stat-sep">·</span>
                <span className="file-detail-stat">
                  <strong>{totalCompliance}</strong> compliance
                </span>
                {totalViolations > 0 && (
                  <>
                    <span className="file-detail-stat-sep">·</span>
                    <span className="file-detail-stat">
                      <strong>1:{Math.round(totalCompliance / totalViolations)}</strong> ratio
                    </span>
                  </>
                )}
              </>
            )}
          </div>
          <CopyButton
            label="Principle fix plan"
            onClick={() => copyToClipboard(buildPrinciplePlanText(principle))}
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
