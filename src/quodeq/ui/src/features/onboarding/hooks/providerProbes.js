/**
 * Run all detection probes and return a normalized result list. Each entry:
 *   { id, classification: 'cli' | 'local-api' | 'cloud', detected, defaultModel? }
 *
 * Concrete probes are imported from the existing settings feature where
 * available. If a probe doesn't exist yet, a stub returns `{ detected: false }`
 * and a TODO points to the right file. The hook's tests mock this whole
 * module's `runDetection` export, so this file's correctness is exercised
 * end-to-end at integration-test time (Task 18) rather than in isolation.
 */

async function detectCliProvider(id) {
  // TODO: replace with the real probe from features/settings/components.
  // CliProviderTab.jsx currently uses `useApi` + react-query (settingsKeys)
  // rather than exposing a standalone detection helper. When that helper is
  // extracted, swap this stub for a delegating call.
  // Expected shape: { id, classification: 'cli', detected: boolean, defaultModel: string | null }
  return { id, classification: 'cli', detected: false };
}

async function detectOllamaDaemon() {
  try {
    const res = await fetch('/api/ollama/health', { method: 'GET' });
    return { id: 'ollama', classification: 'local-api', detected: res.ok, defaultModel: null };
  } catch {
    return { id: 'ollama', classification: 'local-api', detected: false };
  }
}

function detectStoredCloudKey(providerId) {
  try {
    const stored = localStorage.getItem(`cc-${providerId}-api-key`);
    return { id: providerId, classification: 'cloud', detected: Boolean(stored), defaultModel: null };
  } catch {
    return { id: providerId, classification: 'cloud', detected: false };
  }
}

export async function runDetection() {
  const probes = await Promise.allSettled([
    detectCliProvider('codex-cli'),
    detectCliProvider('claude-code'),
    detectOllamaDaemon(),
    detectStoredCloudKey('openai'),
    detectStoredCloudKey('anthropic'),
  ]);
  return probes.map((p) => (p.status === 'fulfilled' ? p.value : { detected: false }));
}
