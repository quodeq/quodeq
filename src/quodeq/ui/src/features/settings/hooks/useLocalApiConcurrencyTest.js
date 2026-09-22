import { useState } from 'react';

/**
 * Shared concurrency-test state (testing/result/error) for the local-API
 * tabs (Omlx/LlamaCpp/Ollama), which were near-identical copies of this
 * before the split. `testFn` is the provider-specific async call (it should
 * do its own logging on failure before rethrowing, so each tab keeps its
 * own console.warn message); the caller is responsible for any pre-flight
 * guard (e.g. "no model picked yet") and for applying `result.recommended`
 * to its own `subagents` state -- this hook only tracks the request itself.
 */
export function useLocalApiConcurrencyTest(testFn) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState(null);

  const runTest = async () => {
    setTesting(true);
    try {
      const result = await testFn();
      setTestResult(result);
      setTestError(null);
      return result;
    } catch (err) {
      setTestResult(null);
      setTestError(err);
      return null;
    } finally {
      setTesting(false);
    }
  };

  return { testing, testResult, testError, runTest };
}
