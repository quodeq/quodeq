import { useState, useEffect } from 'react';
import { scanPath } from '../../../api/index.js';

/**
 * Fetch scan data for a project ID or a raw local path.
 * Pass projectId for existing projects, or localPath for new evaluations.
 * Returns { scanData, loading, error }.
 */
export function useScanData(projectId, localPath) {
  const [scanData, setScanData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const target = projectId || localPath;
    if (!target) {
      setScanData(null);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const fetchPromise = projectId
      ? fetch(`/api/projects/${encodeURIComponent(projectId)}/scan`, { signal: controller.signal }).then((res) => {
          if (!res.ok) throw new Error(`Scan failed: ${res.status}`);
          return res.json();
        })
      : scanPath(localPath);

    fetchPromise
      .then((data) => {
        if (!controller.signal.aborted) {
          setScanData(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => { controller.abort(); };
  }, [projectId, localPath]);

  return { scanData, loading, error };
}
