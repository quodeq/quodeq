import { StatStrip, Stat } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';

/**
 * RepoScanStep.jsx's post-scan summary (file/code/language/branch stats,
 * top languages). Extracted verbatim.
 */
export function RepoScanSummary({ scan }) {
  const totalFiles = scan?.total_files ?? 0;
  const codeFiles = scan?.code_files ?? 0;
  const langs = scan?.languages || {};
  const langCount = Object.keys(langs).length;
  const branchCount = scan?.branches?.length ?? 0;
  const topLangs = Object.entries(langs).sort((a, b) => b[1] - a[1]).slice(0, 8);
  return (
    <div className="onboarding-scan-summary">
      <StatStrip cards>
        <Stat label="FILES" value={totalFiles} hint={t('onboarding.allFilesHint')} />
        <Stat label="CODE" value={codeFiles} hint={t('onboarding.codeFilesHint')} />
        <Stat label="LANGUAGES" value={langCount} />
        <Stat label="BRANCHES" value={branchCount} />
      </StatStrip>
      {topLangs.length > 0 && (
        <div className="onboarding-scan-summary__langs">
          {topLangs.map(([lang, count]) => (
            <span key={lang} className="onboarding-scan-summary__lang-pill">
              <span className="onboarding-scan-summary__lang-name">{lang}</span>
              <span className="onboarding-scan-summary__lang-count">{count}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
