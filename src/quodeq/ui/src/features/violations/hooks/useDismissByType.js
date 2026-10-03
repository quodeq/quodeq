/**
 * Dismiss every finding of one requirement type in a scope, with a confirm
 * step, then fold the mutation into the caches and reconcile.
 */
import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { applyMutationDelta } from '../../../api/applyMutationDelta.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';
import { t } from '../../../strings/index.js';
import { pluralKey } from '../../../utils/plural.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { DISMISS_SCOPE } from '../violationsVocab.js';

/** How many of the row's findings sit in the row's principle. */
export function principleCount(row) {
  return (row.violations || []).filter((v) => v.principle === row.principle).length;
}

function scopePayload(row, scopeKind) {
  return {
    req: row.req,
    dimension: row.dimension,
    runId: row.runId,
    principle: scopeKind === DISMISS_SCOPE.PRINCIPLE ? row.principle : undefined,
  };
}

async function confirmed(row, scopeKind) {
  const count = scopeKind === DISMISS_SCOPE.PRINCIPLE ? principleCount(row) : row.now;
  return confirmDialog({
    title: t('violations.dismissTypeTitle', { req: row.req }),
    message: t(pluralKey(count, 'violations.dismissTypeBodyOne', 'violations.dismissTypeBody'), { count }),
    confirmLabel: t('violations.dismissTypeConfirm'),
  });
}

/**
 * @param {{project: string, selectedSource: string, onReconcile?: Function, bumpDismissRefresh?: Function}} args
 * @returns {{dismissType: (row: Object, scopeKind: string) => Promise<void>, error: string|null, notice: string|null}}
 *   `notice` says when the server dismissed a different number than the row showed.
 */
export function useDismissByType({ project, selectedSource, onReconcile, bumpDismissRefresh }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const isShared = selectedSource === PROJECT_SOURCE.SHARED;

  const dismissType = useCallback(async (row, scopeKind) => {
    if (isShared || !project) return;
    if (!(await confirmed(row, scopeKind))) return;
    try {
      const result = await api.dismissByType(project, scopePayload(row, scopeKind));
      if (result?.delta) applyMutationDelta(queryClient, project, { ...result.delta, dimensions: result.scores?.dimensions });
      onReconcile?.();
      bumpDismissRefresh?.();
      setError(null);
      const expected = scopeKind === DISMISS_SCOPE.PRINCIPLE ? principleCount(row) : row.now;
      setNotice(result?.dismissed === expected ? null : t('violations.dismissTypeCountDiffers', { actual: result?.dismissed ?? 0, expected }));
    } catch (err) {
      console.error('Failed to dismiss by type:', err);
      setError(t('violations.dismissTypeFailed'));
    }
  }, [api, queryClient, project, isShared, onReconcile, bumpDismissRefresh]);

  return { dismissType, error, notice };
}
