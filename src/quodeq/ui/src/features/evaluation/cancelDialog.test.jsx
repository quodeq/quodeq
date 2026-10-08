import { describe, it, expect, vi } from 'vitest';
import { buildCancelEvaluationDialog, confirmCancelEvaluation } from './cancelDialog.js';
import { t } from '../../strings/index.js';

// Stopping a run the app did not start also ends whatever started it (a CI
// job, a terminal command): the dialog says so.
describe('the stop dialog', () => {
  it('names what else an external run belongs to', () => {
    expect(buildCancelEvaluationDialog({ external: true }).message).toBe(t('evaluate.cancelBodyExternal'));
    expect(t('evaluate.cancelBodyExternal')).toMatch(/CI/);
  });

  it('keeps today\'s words for a run the app started', () => {
    expect(buildCancelEvaluationDialog().message).toBe(t('evaluate.cancelBody'));
  });

  it('the default confirm passes the external flag to the dialog', async () => {
    const choose = vi.fn().mockResolvedValue(null);
    await confirmCancelEvaluation(choose, { external: true });
    expect(choose.mock.calls[0][0].message).toBe(t('evaluate.cancelBodyExternal'));
  });
});
