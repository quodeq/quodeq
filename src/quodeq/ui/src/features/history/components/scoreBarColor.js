import { scoreTier } from '../../../models/runRules.js';

const TIER_COLOR_VAR = {
  exemplary: '--color-grade-top-text',
  good: '--color-grade-high-text',
  adequate: '--color-grade-mid-text',
  poor: '--color-grade-low-text',
  unacceptable: '--color-grade-bottom-text',
};

/** CSS variable name for a history bar, from the shared score tiers. */
export function scoreBarColorVar(score) {
  const tier = scoreTier(parseFloat(score));
  return tier ? TIER_COLOR_VAR[tier] : '--color-accent';
}
