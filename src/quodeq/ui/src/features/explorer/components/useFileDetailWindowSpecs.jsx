import { useMemo } from 'react';
import { buildFilePlanText } from '../../../utils/planTextBuilders.js';
import { buildFileReport } from '../../../utils/reportBuilder.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';

function filterTitleSuffix(filter) {
  if (!filter || filter === 'all') return '';
  return ` (${filter})`;
}

/** Registers the file's report + fix-plan side-pane window specs, kept in
 * sync with the active severity filter. */
export function useFileDetailWindowSpecs({ file, activeFilter }) {
  const reportSpec = useMemo(() => {
    if (!file?.file) return null;
    const buildMarkdown = () => buildFileReport(file, activeFilter);
    const filenameLabel = file.file.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    const baseTitle = `${file.file.split('/').pop()} report`;
    return {
      id: `report:file:${file.file}`,
      type: 'report',
      title: `${baseTitle}${filterTitleSuffix(activeFilter)}`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `file-${filenameLabel}-report.md`, body: buildMarkdown() }),
    };
  }, [file, activeFilter]);
  useRegisterWindowSpec('report', reportSpec);

  const fixPlanSpec = useMemo(() => {
    if (!file?.file || (file.total || 0) === 0) return null;
    const buildMarkdown = () => buildFilePlanText(file, activeFilter);
    const filenameLabel = file.file.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    const baseTitle = `${file.file.split('/').pop()} fix plan`;
    return {
      id: `fixplan:file:${file.file}`,
      type: 'fixplan',
      title: `${baseTitle}${filterTitleSuffix(activeFilter)}`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `file-${filenameLabel}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [file, activeFilter]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);
}
