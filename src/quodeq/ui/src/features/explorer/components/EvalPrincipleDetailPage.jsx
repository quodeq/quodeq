import { memo, useState } from 'react';
import { PLAN_TEST_INSTRUCTION_GROUP, PLAN_TEST_INSTRUCTION_SINGLE } from '../../../utils/explorerUtils.js';
import { SEVERITY_ORDER as EVAL_SEVERITY_ORDER, gradeColorClass } from '../../../utils/formatters.js';
import CopyButton from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { EvalViolationCard, ComplianceCard } from './EvalCards.jsx';

const PAGE_SIZE = 20;

function ViolationListSection({ violationsBySeverity, principle, buildViolationPlanText }) {
  return EVAL_SEVERITY_ORDER.map((sev) => {
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
            <EvalViolationCard key={idx} v={v} principle={principle} buildViolationPlanText={buildViolationPlanText} index={idx} />
          ))}
        </div>
      </div>
    );
  });
}

function ComplianceListSection({ compliance, displayedCompliance, hasMoreCompliance, showAllCompliance, setShowAllCompliance, principle }) {
  if (compliance.length === 0) return null;
  return (
    <div>
      <div className="violation-group-header">
        <span className="violation-group-title">Compliance</span>
        <span className="violation-group-count">{compliance.length}</span>
      </div>
      <div className="vlive-violations-group">
        {displayedCompliance.map((c, idx) => (
          <ComplianceCard key={idx} c={c} principle={principle} index={idx} />
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
  );
}

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
        if (v.reason) lines.push('', `**Why it's a violation:** ${v.reason}`);
        const linkedRefs = (v.reqRefs || []).filter(r => r.url && /^https?:\/\//.test(r.url));
        if (linkedRefs.length > 0) lines.push('', `**References:** ${linkedRefs.map(r => `${r.label} (${r.url})`).join(', ')}`);
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
  };

  const buildViolationPlanText = (v) => {
    const loc = v.file ? `${v.file}${v.line ? `:${v.line}` : ''}` : '';
    const lines = [
      `# Fix Request: ${principle}`,
      '',
      `**Severity:** ${v.severity || 'unknown'}`,
    ];
    if (loc) lines.push(`**File:** ${loc}`);
    if (v.snippet) lines.push('', '## Affected Code', '```', v.snippet, '```');
    if (v.reason) lines.push('', "## Why It's a Violation", v.reason);
    if (v.reqRefs?.length > 0) lines.push('', `**References:** ${v.reqRefs.map(r => `${r.label} (${r.url})`).join(', ')}`);
    else if (v.req) lines.push('', `**Requirement:** ${v.req}`);
    lines.push('', '---', 'Please provide a concrete, step-by-step fix for this specific violation.');
    if (loc) lines.push(`Apply it to \`${loc}\`.`);
    lines.push(PLAN_TEST_INSTRUCTION_SINGLE);
    return lines.join('\n').trim();
  };

  const sevCounts = { critical: 0, major: 0, minor: 0 };
  violations.forEach(v => { const s = (v.severity || 'minor').toLowerCase(); if (sevCounts[s] !== undefined) sevCounts[s]++; });

  return (
    <>
      <section className="panel file-detail-summary-panel">
        <div className="file-detail-stats-row">
          <div className="file-detail-stats">
            <h3 className="file-detail-title" style={{ margin: 0 }}>{principle}</h3>
            {grade === 'Insufficient' ? (
              <span className="exec-summary-insufficient">Not enough evidence</span>
            ) : (
              <>
                {score && (
                  <>
                    <span className="file-detail-stat-sep">·</span>
                    <span className="file-detail-stat" style={{ fontSize: '1.1rem' }}><strong>{score.replace('/10', '')}</strong></span>
                  </>
                )}
                <span className="file-detail-stat-sep">·</span>
                <span className={`chip small ${gradeColorClass(grade)}`}>{grade || '—'}</span>
              </>
            )}
          </div>
          {violations.length > 0 && (
            <CopyButton
              label="Principle fix plan"
              onClick={() => copyToClipboard(buildPrinciplePlanText())}
            />
          )}
        </div>
        <div className="file-detail-stats" style={{ marginTop: 6 }}>
          {sevCounts.critical > 0 && (
            <span className="file-detail-stat severity-tag critical">{sevCounts.critical} critical</span>
          )}
          {sevCounts.major > 0 && (
            <span className="file-detail-stat severity-tag major">{sevCounts.major} major</span>
          )}
          {sevCounts.minor > 0 && (
            <span className="file-detail-stat severity-tag minor">{sevCounts.minor} minor</span>
          )}
          {(sevCounts.critical > 0 || sevCounts.major > 0 || sevCounts.minor > 0) && <span className="file-detail-stat-sep">·</span>}
          <span className="file-detail-stat"><strong>{violations.length}</strong> violations</span>
          {compliance.length > 0 && (
            <>
              <span className="file-detail-stat-sep">·</span>
              <span className="file-detail-stat"><strong>{compliance.length}</strong> compliance</span>
              {violations.length > 0 && (
                <>
                  <span className="file-detail-stat-sep">·</span>
                  <span className="file-detail-stat"><strong>1:{Math.round(compliance.length / violations.length)}</strong> ratio</span>
                </>
              )}
            </>
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

      <ViolationListSection violationsBySeverity={violationsBySeverity} principle={principle} buildViolationPlanText={buildViolationPlanText} />

      <ComplianceListSection
        compliance={compliance} displayedCompliance={displayedCompliance}
        hasMoreCompliance={hasMoreCompliance} showAllCompliance={showAllCompliance}
        setShowAllCompliance={setShowAllCompliance} principle={principle}
      />
    </>
  );
});

export default EvalPrincipleDetailPage;
