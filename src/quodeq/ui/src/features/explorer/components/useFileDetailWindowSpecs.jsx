import { useMemo } from 'react';
import { buildFilePlanText } from '../../../utils/planTextBuilders.js';
import { buildFileReport } from '../../../utils/reportBuilder.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import { filterTitleSuffix } from './usePrincipleReportSpec.jsx';

// Both windows are the same document with a different builder: the same
// title stem, the same filter suffix, the same render/copy/download trio, and
// a download name built from the same slugged path.
function buildFileWindowSpec({ file, activeFilter, kind, titleWord, fileSuffix, buildMarkdown }) {
  const filenameLabel = file.file.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
  const baseTitle = `${file.file.split('/').pop()} ${titleWord}`;
  return {
    id: `${kind}:file:${file.file}`,
    type: kind,
    title: `${baseTitle}${filterTitleSuffix(activeFilter)}`,
    render: () => <ReportContent markdown={buildMarkdown()} />,
    copy: () => buildMarkdown(),
    download: () => ({ filename: `file-${filenameLabel}-${fileSuffix}.md`, body: buildMarkdown() }),
  };
}

/** Registers the file's report + fix-plan side-pane window specs, kept in
 * sync with the active severity filter. */
export function useFileDetailWindowSpecs({ file, activeFilter }) {
  const reportSpec = useMemo(() => {
    if (!file?.file) return null;
    return buildFileWindowSpec({
      file,
      activeFilter,
      kind: 'report',
      titleWord: 'report',
      fileSuffix: 'report',
      buildMarkdown: () => buildFileReport(file, activeFilter),
    });
  }, [file, activeFilter]);
  useRegisterWindowSpec('report', reportSpec);

  const fixPlanSpec = useMemo(() => {
    if (!file?.file || (file.total || 0) === 0) return null;
    return buildFileWindowSpec({
      file,
      activeFilter,
      kind: 'fixplan',
      titleWord: 'fix plan',
      fileSuffix: 'fix-plan',
      buildMarkdown: () => buildFilePlanText(file, activeFilter),
    });
  }, [file, activeFilter]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);
}
