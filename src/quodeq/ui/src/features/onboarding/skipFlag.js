import { removeKey } from '../../adapters/storage.js';
import { SKIPPED_KEY } from './wizardSteps.js';

/**
 * Forget that the user once skipped the onboarding wizard.
 *
 * Every deliberate way back into the welcome (the empty state's tour button,
 * Settings' "show the welcome again") clears the flag first, so the wizard's
 * own auto-open logic treats the next first-run situation afresh.
 */
export function clearOnboardingSkip() {
  removeKey(SKIPPED_KEY);
}
