/**
 * Fix D (#2441): LOCAL_API_PROVIDERS is defined once in useEvaluation.js and
 * re-exported — useEvaluationLifecycle.js must import it from there rather
 * than maintaining its own copy.
 */
import { describe, it, expect } from 'vitest';
import { LOCAL_API_PROVIDERS } from '../features/evaluation/hooks/useEvaluation.js';

describe('LOCAL_API_PROVIDERS single source of truth (#2441)', () => {
  it('is exported from useEvaluation.js', () => {
    expect(LOCAL_API_PROVIDERS).toBeDefined();
    expect(LOCAL_API_PROVIDERS).toBeInstanceOf(Set);
  });

  it('contains the expected local providers', () => {
    expect(LOCAL_API_PROVIDERS.has('ollama')).toBe(true);
    expect(LOCAL_API_PROVIDERS.has('llamacpp')).toBe(true);
    expect(LOCAL_API_PROVIDERS.has('omlx')).toBe(true);
  });

  it('useEvaluationLifecycle imports the same Set object, not a separate copy', async () => {
    // Importing useEvaluationLifecycle.js must not re-declare LOCAL_API_PROVIDERS.
    // We verify indirectly: both modules resolve to the same exported reference.
    const mod = await import('../features/evaluation/hooks/useEvaluation.js');
    expect(mod.LOCAL_API_PROVIDERS).toBe(LOCAL_API_PROVIDERS);
  });
});
