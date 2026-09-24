// Local-server online/offline status: written by each local-provider poll
// hook (useOmlxServerStatus.js, useOllamaServerStatus.js,
// useLlamacppServerStatus.js) and read by ServerSection.jsx,
// useInvalidateOnOnline.js, LocalApiTabLayout.jsx and ServerStatusPill.jsx.
// No Python mirror: these hooks poll a local status endpoint and normalize
// its response into this pair themselves (see llm_bridge health checks for
// the Python-side "ok" constant, a different vocabulary).
export const SERVER_STATUS = Object.freeze({ ONLINE: 'online', OFFLINE: 'offline' });
