import { useQuery } from '@tanstack/react-query';
import { scanPath } from '../../../api/index.js';
import { projectKeys } from '../../../api/queryKeys.js';

/**
 * Fetch scan data for a project ID or a raw local path.
 * Pass projectId for existing projects, or localPath for new evaluations.
 * Returns { scanData, loading, error }.
 */
export function useScanData(projectId, localPath) {
  const target = projectId || localPath || null;
  const { data, isLoading, error } = useQuery({
    queryKey: projectId
      ? [...projectKeys.project(projectId), 'scan']
      : ['project', 'scan-path', localPath || ''],
    queryFn: async ({ signal }) => {
      if (projectId) {
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/scan`, { signal });
        if (!res.ok) throw new Error(`Scan failed: ${res.status}`);
        return res.json();
      }
      return scanPath(localPath);
    },
    enabled: !!target,
  });

  return {
    scanData: data ?? null,
    loading: !!target && isLoading,
    error: error ? error.message : null,
  };
}
