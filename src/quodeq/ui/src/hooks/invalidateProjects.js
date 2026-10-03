import { projectsKeys } from '../api/queryKeys.js';

/** The one way to say "the project set changed": refetch the list everywhere. */
export function invalidateProjects(queryClient) {
  return queryClient.invalidateQueries({ queryKey: projectsKeys.list() });
}
