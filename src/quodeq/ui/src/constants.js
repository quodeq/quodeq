export const ISO_25010_URL = 'https://www.iso.org/';

// Settings defaults & localStorage keys (shared by SettingsPage + useEvaluation)
export const DEFAULT_MAX_SUBAGENTS = 5;
export const DEFAULT_POOL_BUDGET = 600;
export const SUBAGENTS_STORAGE_KEY = 'cc-max-subagents';
export const POOL_BUDGET_STORAGE_KEY = 'cc-pool-budget';

export const AI_CMD_STORAGE_KEY = 'cc-ai-cmd';
export const PER_DIMENSION_STORAGE_KEY = 'cc-per-dimension';

export const ACTIVE_PROVIDER_KEY = 'cc-active-provider';

export function providerKey(providerId, setting) {
  return `cc-${providerId}-${setting}`;
}

export const VISIBLE_STANDARDS_STORAGE_KEY = 'quodeq-visible-standards';
export const DEFAULT_VISIBLE_STANDARDS = [
  'security', 'reliability', 'maintainability', 'performance', 'usability', 'flexibility',
];
