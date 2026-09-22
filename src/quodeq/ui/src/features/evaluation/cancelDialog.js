/**
 * View-layer spec for the cancel-evaluation confirmation dialog.
 *
 * useEvaluation used to build this spec (title, labels, per-button variant)
 * inline and await chooseDialog itself, coupling the business action to one
 * presentation widget. The hook now only receives the chosen action key; the
 * presentation choices live here so a different UI can supply its own
 * `confirm` without duplicating the cancel rule.
 */
import { chooseDialog } from '../../utils/chooseDialog.js';
import { t } from '../../strings/index.js';

/**
 * Three-button form: dismiss + two cancel variants. The title carries the
 * "cancel evaluation" verb so the button labels can be terse and describe
 * the side-effect on findings, not repeat the cancel intent. Only the
 * destructive option ('discard') is rendered red; 'keep' and 'dismiss' are
 * neutral so they don't compete visually.
 *
 * @returns {{ title: string, message: string, cancelLabel: string, actions: Array<{key: string, label: string, variant: string}> }}
 */
export function buildCancelEvaluationDialog() {
  return {
    title: t('evaluate.cancelTitle'),
    message: t('evaluate.cancelBody'),
    cancelLabel: t('evaluate.keepRunning'),
    actions: [
      { key: 'preserve', label: t('evaluate.keepFindings'), variant: 'default' },
      { key: 'discard', label: t('evaluate.discardFindings'), variant: 'danger' },
    ],
  };
}

/**
 * Default confirmation flow: show the dialog and resolve the user's choice.
 *
 * @param {(spec: Object) => Promise<string|null>} [choose] dialog runner
 *   (injectable for tests; defaults to the DOM chooseDialog).
 * @returns {Promise<'preserve'|'discard'|null>} null means "keep running".
 */
export function confirmCancelEvaluation(choose = chooseDialog) {
  return choose(buildCancelEvaluationDialog());
}
