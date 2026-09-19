import { StatStrip, Stat } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';

const TOP_LANGUAGES_LIMIT = 8; // the chip row stays one glance; the rest is noise for a summary

/**
 * RepoScanStep.jsx's post-scan summary (file/code/language/branch stats,
 * top languages). Extracted verbatim.
 */
export function RepoScanSummary({ scan }) {
  const totalFiles = scan?.total_files ?? 0;
  const codeFiles = scan?.code_files ?? 0;
  const untrackedFiles = scan?.untracked_files ?? 0;
  // The FILES tile counts what the run will score (git-tracked only, #1209);
  // when git left files out, say how many so the smaller total has a reason.
  const filesHint = untrackedFiles > 0
    ? t('onboarding.untrackedFilesHint', { count: untrackedFiles })
    : t('onboarding.allFilesHint');
  const langs = scan?.languages || {};
  const langCount = Object.keys(langs).length;
  const branchCount = scan?.branches?.length ?? 0;
  const topLangs = Object.entries(langs).sort((a, b) => b[1] - a[1]).slice(0, TOP_LANGUAGES_LIMIT);
  return (
    <div className="onboarding-scan-summary">
      <StatStrip cards>
        <Stat label="FILES" value={totalFiles} hint={filesHint} />
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
