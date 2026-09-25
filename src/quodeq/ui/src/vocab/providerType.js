// Mirror of src/quodeq/core/types/provider.py:ProviderType: how quodeq talks
// to a provider, a CLI tool on PATH or an HTTP API. getAiClients()'s
// per-client `type` field carries it; onboarding's providerProbes.js and
// settings' providerUtils.js read it back.
export const PROVIDER_TYPE = Object.freeze({ CLI: 'cli', API: 'api' });
