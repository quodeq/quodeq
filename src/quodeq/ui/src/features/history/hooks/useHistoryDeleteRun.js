import { confirmDialog } from '../../../utils/confirmDialog.js';
import { t } from '../../../strings/index.js';

/**
 * HistoryPage.jsx's run-delete handler, extracted verbatim.
 */
export function useHistoryDeleteRun({ selectedSource, deleteEvaluation, onRunDeleted }) {
  async function handleDeleteRun(runId, dateLabel) {
    // Defense in depth: shared-repo runs have no delete route on the backend
    // (mutation is local-only by design, same as dismiss/restore/verify). The
    // real gate is the wiring below (onDeleteRun is undefined when source is
    // 'shared', so the row never renders a delete button), but this early
    // return covers any caller that reaches the handler directly.
    if (selectedSource !== 'local') return;
    const label = dateLabel || runId;
    const ok = await confirmDialog({
      title: t('history.deleteRunConfirmTitle'),
      message: t('history.deleteRunConfirmMsg', { label }),
      confirmLabel: t('violations.delete'),
      cancelLabel: t('history.keep'),
      variant: 'danger',
    });
    if (!ok) return;
    const jobId = runId.startsWith('ext-') ? runId : `ext-${runId}`;
    try {
      await deleteEvaluation(jobId);
    } catch (err) {
      alert(t('history.deleteRunFailed', { message: err.message || t('history.unknownError') }));
      return;
    }
    onRunDeleted?.(runId);
  }

  return handleDeleteRun;
}
