import { useEffect, useState } from 'react';
import { runDetection } from './providerProbes.js';

const PRIORITY = ['codex-cli', 'claude-code', 'ollama', 'openai', 'anthropic'];

function rank(results) {
  // Filter to detected; sort by PRIORITY index (lower = higher priority).
  return results
    .filter((r) => r && r.detected)
    .sort((a, b) => PRIORITY.indexOf(a.id) - PRIORITY.indexOf(b.id));
}

export function useProviderDetection() {
  const [status, setStatus] = useState('detecting');
  const [results, setResults] = useState([]);
  const [preselection, setPreselection] = useState(null);

  useEffect(() => {
    let cancelled = false;
    runDetection().then((res) => {
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
    });
    return () => { cancelled = true; };
  }, []);

  return { status, results, preselection };
}
