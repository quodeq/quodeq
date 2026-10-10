import CopyButton from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import DimRow from './DimRow.jsx';
import { SHORT_SHA } from '../externalRun.js';
import { t, LOCALE } from '../../../strings/index.js';


// "17:36" in the viewer's clock; null for a missing or unreadable time.
function clockTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' });
}

const count = (n) => Number(n || 0).toLocaleString(LOCALE);

// One dimension's figures, missing fields read as zero.
function dimFigures(d) {
  const taken = d?.files?.taken ?? 0;
  const total = d?.files?.total ?? 0;
  return { cached: d?.filesCached ?? 0, taken, toGo: Math.max(0, total - taken), passed: d?.compliance ?? 0 };
}

// The repository's figures, summed over the run's dimensions. Every
// dimension caches the same files, so "unchanged" is the largest cache.
function repositoryFigures(progress) {
  const sum = { cached: 0, analyzed: 0, toGo: 0, passed: 0 };
  for (const d of progress?.dimensions || []) {
    const f = dimFigures(d);
    sum.cached = Math.max(sum.cached, f.cached);
    sum.analyzed += f.taken;
    sum.toGo += f.toGo;
    sum.passed += f.passed;
  }
  return { source: progress?.projectFiles ?? 0, ...sum };
}

function Pair({ label, children }) {
  return (
    <span className="scan-progress__pair">
      <span className="scan-progress__pair-label">{label}</span>
      <span className="scan-progress__pair-value">{children}</span>
    </span>
  );
}

function RunBlock({ job }) {
  const started = clockTime(job.startedAt);
  const finishesBy = clockTime(job.deadlineAt);
  return (
    <div className="scan-progress__pairs">
      <Pair label={t('evaluate.detailJobId')}>
        <code className="eval-identity__code">{job.jobId}</code>
        <CopyButton aria-label={t('evaluate.copyJobIdAria')} onClick={() => copyToClipboard(job.jobId)} />
      </Pair>
      {started && <Pair label={t('evaluate.detailStarted')}>{started}</Pair>}
      {finishesBy && <Pair label={t('evaluate.detailFinishesBy')}>{finishesBy}</Pair>}
      {job.commitSha && <Pair label={t('evaluate.detailCommit')}>{job.commitSha.slice(0, SHORT_SHA)}</Pair>}
    </div>
  );
}

function RepositoryBlock({ progress }) {
  const f = repositoryFigures(progress);
  return (
    <div className="scan-progress__pairs">
      <Pair label={t('evaluate.detailSourceFiles')}>{count(f.source)}</Pair>
      <Pair label={t('evaluate.detailCached')}>{count(f.cached)}</Pair>
      <Pair label={t('evaluate.detailAnalyzed')}>{count(f.analyzed)}</Pair>
      <Pair label={t('evaluate.detailToGo')}>{count(f.toGo)}</Pair>
      <Pair label={t('evaluate.detailChecksPassed')}>{count(f.passed)}</Pair>
    </div>
  );
}

/**
 * What "details" opens under the run bar: the run itself (job id, start,
 * deadline, commit), the repository's real file figures, then the existing
 * per-dimension rows. Kept out of the default view.
 */
export default function ScanProgressDetail({ job, progress, id }) {
  const dims = progress?.dimensions || [];
  return (
    <div className="scan-progress__expanded" id={id}>
      <div className="scan-progress__expanded-label">{t('evaluate.detailRun')}</div>
      <RunBlock job={job} />
      <div className="scan-progress__expanded-label">{t('evaluate.detailRepository')}</div>
      <RepositoryBlock progress={progress} />
      {dims.length > 0 && <div className="scan-progress__expanded-label">{t('evaluate.perDimension')}</div>}
      {dims.map((d) => <DimRow key={d.id} dim={d} />)}
    </div>
  );
}
