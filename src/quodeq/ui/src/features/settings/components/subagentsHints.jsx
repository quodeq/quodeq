/**
 * The max-parallel-agents row's help-hint copy, shared by the remote
 * (CLI/cloud) tabs and the Ollama local-API tab. Its own module so the
 * generic settings-row building blocks (settingsRowParts.jsx) don't have to
 * import a specific provider-tab file for it.
 */
import { t } from '../../../strings/index.js';

export const SUBAGENTS_HINT_REMOTE = (
  <>
    <p>{t('settings.subagentsHintRemoteP1')}</p>
    <p>{t('settings.subagentsHintRemoteP2')}</p>
  </>
);

export const SUBAGENTS_HINT_OLLAMA = (
  <>
    <p>{t('settings.subagentsHintOllamaP1')}</p>
    <p>{t('settings.subagentsHintOllamaP2')}</p>
  </>
);
