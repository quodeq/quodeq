import { useMemo } from 'react';
import { cachedFileTree } from '../viz/core/layoutCache.js';
import { findSubtree, buildBreadcrumbPath } from './mapTree.js';

/** The file tree built from the filtered dimensions, plus the current node
 * and breadcrumb for `currentPath`, and the drill/breadcrumb-nav handlers. */
export function useMapTreeState({ filteredDimensions, currentPath, setCurrentPath }) {
  const fullTree = useMemo(() => cachedFileTree(filteredDimensions), [filteredDimensions]);
  const currentNode = useMemo(() => findSubtree(fullTree, currentPath), [fullTree, currentPath]);
  const breadcrumb = useMemo(() => buildBreadcrumbPath(fullTree, currentPath), [fullTree, currentPath]);

  const handleDrillDown = (nodePath) => setCurrentPath(nodePath);
  const handleBreadcrumbNav = (path) => setCurrentPath(path);

  return { fullTree, currentNode, breadcrumb, handleDrillDown, handleBreadcrumbNav };
}
