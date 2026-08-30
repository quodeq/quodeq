import test from 'node:test';
import assert from 'node:assert/strict';
import { providerSupportsWebTools, WEB_TOOL_PROVIDERS } from './provider.js';

test('WEB_TOOL_PROVIDERS: exact membership (mirrors the backend gate)', () => {
  assert.deepEqual([...WEB_TOOL_PROVIDERS].sort(), ['claude', 'llamacpp', 'ollama', 'omlx']);
});

test('providerSupportsWebTools: true for every member', () => {
  assert.equal(providerSupportsWebTools('claude'), true);
  assert.equal(providerSupportsWebTools('ollama'), true);
  assert.equal(providerSupportsWebTools('omlx'), true);
  assert.equal(providerSupportsWebTools('llamacpp'), true);
});

test('providerSupportsWebTools: false for a non-member cloud provider', () => {
  assert.equal(providerSupportsWebTools('openai'), false);
  assert.equal(providerSupportsWebTools('anthropic-api'), false);
});

test('providerSupportsWebTools: false for undefined/null (no provider selected yet)', () => {
  assert.equal(providerSupportsWebTools(undefined), false);
  assert.equal(providerSupportsWebTools(null), false);
});
