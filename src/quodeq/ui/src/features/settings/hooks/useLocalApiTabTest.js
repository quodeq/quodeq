/**
 * The concurrency-test wiring the local-API provider tabs share.
 *
 * Ollama, llama.cpp and MLX all offer the same "auto-detect" affordance: run
 * the provider's concurrency probe, show a translated message if it fails,
 * and write a recommended agent count back into the settings state. Only the
 * probe call, the log label and the message key differ per provider.
 */
import { useLocalApiConcurrencyTest } from './useLocalApiConcurrencyTest.js';
import { t } from '../../../strings/index.js';

/**
 * Wire a provider tab's auto-detect button.
 *
 * @param {Object} options
 * @param {() => Promise<Object>} options.probe The provider's concurrency probe.
 * @param {string} options.warnLabel console.warn label used when the probe throws.
 * @param {string} options.errorKey Translation key for the message shown on failure.
 * @param {(field: string, value: string) => void} options.update Settings updater.
 * @param {boolean} [options.enabled=true] When false, the button's handler is a no-op.
 * @returns {{testing: boolean, testResult: Object|null, testError: string|null, onRunTest: () => Promise<void>}}
 *   Ready to spread onto LocalApiAdvancedPanel.
 */
export function useLocalApiTabTest({ probe, warnLabel, errorKey, update, enabled = true }) {
  const { testing, testResult, testError: rawTestError, runTest: runConcurrencyTest } = useLocalApiConcurrencyTest(
    () => probe().catch((err) => {
      console.warn(warnLabel, err);
      throw err;
    }),
  );
  const onRunTest = async () => {
    if (!enabled) return;
    const result = await runConcurrencyTest();
    if (result?.recommended) update('subagents', String(result.recommended));
  };
  return {
    testing,
    testResult,
    testError: rawTestError ? t(errorKey) : null,
    onRunTest,
  };
}
