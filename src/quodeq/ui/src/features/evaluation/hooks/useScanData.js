import { useState, useEffect } from 'react';

/**
 * Fetch scan data (branches, modules) for a project.
 * Returns { scanData, loading, error }.
 */
export function useScanData(projectId) {
  const [scanData, setScanData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!projectId) {
      setScanData(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/projects/${encodeURIComponent(projectId)}/scan`)
      .then((res) => {
        if (!res.ok) throw new Error(`Scan failed: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!cancelled) {
          setScanData(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [projectId]);

  return { scanData, loading, error };
}
