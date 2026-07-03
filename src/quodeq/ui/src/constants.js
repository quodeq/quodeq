export const ISO_25010_URL = 'https://www.iso.org/';

// Settings defaults & localStorage keys (shared by SettingsPage + useEvaluation).
// These client-side defaults can be overridden by server config (ai_providers.json).
export const DEFAULT_MAX_SUBAGENTS = 5;
export const DEFAULT_TIME_LIMIT_S = 600;
export const MIN_SUBAGENTS = 1;
export const MAX_SUBAGENTS = 10;
export const DEFAULT_SUBAGENTS = 5;
export const SUBAGENTS_STORAGE_KEY = 'cc-max-subagents';
export const TIME_LIMIT_STORAGE_KEY = 'cc-time-limit';

export const AI_CMD_STORAGE_KEY = 'cc-ai-cmd';
export const PER_DIMENSION_STORAGE_KEY = 'cc-per-dimension';

export const ACTIVE_PROVIDER_KEY = 'cc-active-provider';

export function providerKey(providerId, setting) {
  return `cc-${providerId}-${setting}`;
}

// Fired (same-tab) whenever any provider setting is written — the analysis
// active-provider or a per-provider model. The assistant gate listens for it
// so that in Default mode (which mirrors the analysis provider/model) the
// displayed model updates live when the user changes it in Settings. The
// native 'storage' event only fires cross-tab, so we need this in-tab signal.
export const PROVIDER_SETTINGS_CHANGED_EVENT = 'cc-provider-settings-changed';

export function notifyProviderSettingsChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(PROVIDER_SETTINGS_CHANGED_EVENT));
  }
}

export const VISIBLE_STANDARDS_STORAGE_KEY = 'quodeq-visible-standards';
export const DEFAULT_VISIBLE_STANDARDS = [
  'security', 'reliability', 'maintainability', 'performance', 'usability', 'flexibility',
];

export const SCORE_HISTORY_GRANULARITY_STORAGE_KEY = 'quodeq-score-history-granularity';
export const SCORE_HISTORY_GRANULARITIES = ['day', 'week', 'month'];
export const DEFAULT_SCORE_HISTORY_GRANULARITY = 'day';
