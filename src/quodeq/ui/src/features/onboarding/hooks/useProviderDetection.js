import { useEffect, useState } from 'react';
import { runDetection } from './providerProbes.js';

const PRIORITY = ['codex-cli', 'claude-code', 'ollama', 'openai', 'anthropic'];

function rank(results) {
  // Filter to detected; sort by PRIORITY index (lower = higher priority).
  return results
    .filter((r) => r && r.detected)
    .sort((a, b) => PRIORITY.indexOf(a.id) - PRIORITY.indexOf(b.id));
}

/**
 * Detects which providers are usable on this machine and picks the best one to
 * preselect in the wizard.
 *
 * `status` moves from 'detecting' to 'detected', 'none' or 'error'. Results
 * arriving after unmount are dropped.
 *
 * `detect` defaults to `runDetection` and is injectable so a test can supply
 * a fake without mocking the module.
 *
 * @param {{ detect?: () => Promise<object[]> }} [deps]
 * @returns {{status: string, results: object[], preselection: {id: string, classification: string, model: string|null}|null}}
 */
export function useProviderDetection({ detect = runDetection } = {}) {
  const [status, setStatus] = useState('detecting');
  const [results, setResults] = useState([]);
  const [preselection, setPreselection] = useState(null);

  useEffect(() => {
    let cancelled = false;
    detect().then((res) => {
      if (cancelled) return;
      const ranked = rank(res);
      setResults(res);
      if (ranked.length === 0) {
        setStatus('none');
        setPreselection(null);
      } else {
        setStatus('detected');
        const top = ranked[0];
        setPreselection({ id: top.id, classification: top.classification, model: top.defaultModel || null });
      }
    }).catch(() => {
      if (cancelled) return;
      setStatus('error');
    });
    return () => { cancelled = true; };
  }, []);

  return { status, results, preselection };
}
