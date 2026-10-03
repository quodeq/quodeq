import { OllamaLogContext } from './OllamaLogContext.js';
import { useOllamaLogStream } from './useOllamaLogStream.js';
import { useLogWindow } from '../_shared/useLogWindow.js';
import { makeProviderLogSpec } from '../_shared/providerLogSpec.jsx';
import { t } from '../../../strings/index.js';

const WINDOW_ID = 'ollama-log';

const buildSpec = makeProviderLogSpec({ windowId: WINDOW_ID, title: () => t('settings.ollamaLogTitle') });

export function OllamaLogProvider({ children }) {
  const value = useLogWindow({ windowId: WINDOW_ID, useLogSource: useOllamaLogStream, buildSpec });
  return <OllamaLogContext.Provider value={value}>{children}</OllamaLogContext.Provider>;
}
