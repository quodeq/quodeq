// Local-server online/offline status: written by each local-provider poll
// hook (useOmlxServerStatus.js, useOllamaServerStatus.js,
// useLlamacppServerStatus.js) and read by ServerSection.jsx,
// useInvalidateOnOnline.js, LocalApiTabLayout.jsx and ServerStatusPill.jsx.
// No Python mirror: these hooks poll a local status endpoint and normalize
// its response into this pair themselves (see llm_bridge health checks for
// the Python-side "ok" constant, a different vocabulary).
export const SERVER_STATUS = Object.freeze({ ONLINE: 'online', OFFLINE: 'offline' });

// The two modes stored under useAssistantProvider.js's ASSISTANT_MODE_KEY:
// DEFAULT mirrors the analysis gate live, CUSTOM uses the assistant-scoped
// provider/model. Lives here, not on the hook, since useAssistantProvider.js
// is fully mocked (vi.mock) in AssistantDrawerProvider.write.test.jsx and
// useAssistantContext.test.jsx, which would make a value defined there
// invisible to them.
export const ASSISTANT_MODE = Object.freeze({ DEFAULT: 'default', CUSTOM: 'custom' });
