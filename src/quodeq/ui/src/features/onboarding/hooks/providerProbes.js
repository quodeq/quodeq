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

// Onboarding-side IDs differ from the server's ai_providers.json IDs.
const CLI_SERVER_ID = { 'codex-cli': 'codex', 'claude-code': 'claude' };
/** How long each detection probe waits before aborting its fetch. */
export const PROBE_TIMEOUT_MS = 5000;

// Every probe is a timed GET whose failure is "not detected", never an
// error the caller has to handle: one unreachable provider must not fail the
// whole detection pass. `read` turns a successful response into the probe's
// own detected/defaultModel shape.
async function probe(id, classification, url, read) {
  const miss = { id, classification, detected: false, defaultModel: null };
  try {
    const res = await fetch(url, { method: 'GET', signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) });
    if (!res.ok) return miss;
    return { id, classification, ...(await read(res)) };
  } catch (err) {
    console.warn(`[providerProbes] ${classification} probe failed:`, err);
    return miss;
  }
}

async function detectCliProvider(id) {
  const serverId = CLI_SERVER_ID[id] || id;
  return probe(id, 'cli', '/api/ai-clients', async (res) => {
    const data = await res.json();
    const detected = (data.clients || []).some((c) => c.id === serverId && c.type === 'cli' && c.installed !== false);
    return { detected, defaultModel: null };
  });
}

// The only probe whose answer is the response status itself: a reachable
// health endpoint means the daemon is up.
async function detectOllamaDaemon() {
  return probe('ollama', 'local-api', '/api/ollama/health', () => ({ detected: true, defaultModel: null }));
}

async function detectStoredCloudKey(providerId) {
  return probe(providerId, 'cloud', `/api/provider/key-status?provider=${encodeURIComponent(providerId)}`, async (res) => {
    const data = await res.json();
    return { detected: Boolean(data.configured), defaultModel: null };
  });
}

/**
 * Probes every supported provider in parallel and returns one result per
 * probe. A probe that throws reports as not detected, so one broken provider
 * cannot fail the whole detection pass.
 *
 * @returns {Promise<Array<{id?: string, classification?: string, detected: boolean, defaultModel?: string|null}>>}
 */
export async function runDetection() {
  const probes = await Promise.allSettled([
    detectCliProvider('codex-cli'),
    detectCliProvider('claude-code'),
    detectCliProvider('copilot'),
    detectOllamaDaemon(),
    detectStoredCloudKey('openai'),
    detectStoredCloudKey('anthropic'),
  ]);
  return probes.map((p) => (p.status === 'fulfilled' ? p.value : { detected: false }));
}
