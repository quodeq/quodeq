import { useEffect, useMemo } from 'react';
import { invalidateThemeColors } from '../core/galaxyCore.js';
import VizBreadcrumb from './VizBreadcrumb.jsx';
import MapLegend, { VizTooltipAnchor } from './MapLegend.jsx';
import { buildLevelInfo } from './galaxyFolderScene.js';
import { createEventHandlers } from './galaxyFolderEvents.js';
import { useGalaxyFolderNav } from './useGalaxyFolderNav.js';
import { useGalaxyFolderCamera } from './useGalaxyFolderCamera.js';
import { LevelInfoPanel } from './galaxyViewInfo.jsx';
import GalaxyCanvas, { useFadeIn } from './GalaxyCanvas.jsx';
import ChartKeyboardControls from '../../../../components/ChartKeyboardControls.jsx';
import { t } from '../../../../strings/index.js';
import { riskBubbleKey } from './riskBubbleName.js';

// One control per star, folders included, since the canvas hit-tests both.
// Capped because a folder with hundreds of entries would bury the rest of
// the page's tab order.
const GALAXY_KBD_MAX = 100;

/** Keyboard-reachable stand-ins for the stars the canvas hit-tests. Each item
 * carries the star's path, which is what activateStar resolves on: a star with
 * neither path nor name is skipped, since no key would ever match it. */
function starItems(scene, activateStar) {
  const stars = (scene?.rootStars || []).slice(0, GALAXY_KBD_MAX);
  return stars.filter((s) => s.path || s.name).map((s) => {
    const key = s.path || s.name;
    return {
      key,
      text: s.isFolder
        ? t('map.galaxyKbdFolderItem', { name: s.name })
        : t(riskBubbleKey(s.violations), { file: s.name, count: s.violations || 0 }),
      onActivate: () => activateStar(key),
    };
  });
}

/** Breadcrumb parts for the current nav path — project name first, then
 * one entry per folder drilled into. */
function useFolderBreadcrumb(refs, projectName, navVersion) {
  return useMemo(() => {
    const path = refs.navRef.current.path;
    const parts = [{ label: projectName || 'Project', idx: 0 }];
    for (let i = 1; i < path.length; i++) {
      parts.push({ label: path[i].name, idx: i });
    }
    return parts;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectName, navVersion]);
}

/** Composes nav + camera + event handlers + the breadcrumb/level-info view
 * data everything below renders from. */
function useGalaxyFolderViewModel({ node, currentPath, onPathChange, onFileClick, showLabels, resetKey, projectName }) {
  const {
    refs, currentNode, scene, navVersion, setNavVersion, saveNav, startTransition,
  } = useGalaxyFolderNav({ node, currentPath, onPathChange, resetKey });

  // The animation loop bumps navVersion itself on fly-completion and via
  // advanceCamera's own auto-enter path, so it shares the nav hook's setter.
  const { size, getFitZoom } = useGalaxyFolderCamera({ refs, scene, showLabels, saveNav, setNavVersion });

  const handlers = useMemo(
    () => createEventHandlers(refs, { startTransition, saveNav, getFitZoom, scene, size }),
    [refs, startTransition, saveNav, getFitZoom, scene, size]
  );

  const breadcrumb = useFolderBreadcrumb(refs, projectName, navVersion);

  const levelInfo = useMemo(() => buildLevelInfo({
    scene, currentNode, zoomedFileRef: refs.zoomedFileRef, navRef: refs.navRef, projectName, onFileClick,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [scene, currentNode, projectName, onFileClick, navVersion]);

  return { refs, scene, size, handlers, breadcrumb, levelInfo };
}

/** Fixed-position tooltip + the bottom-left legend strip. */
function GalaxyFolderOverlays({ tooltipRef }) {
  return (
    <>
      <VizTooltipAnchor tooltipRef={tooltipRef} />
      <MapLegend />
    </>
  );
}

export default function GalaxyFolderView({ node, currentPath = '', onPathChange, onFileClick, showLabels = true, darkMode, resetKey = 0, projectName = '' }) {
  useEffect(() => { invalidateThemeColors(); }, [darkMode]);

  const { refs, scene, size, handlers, breadcrumb, levelInfo } = useGalaxyFolderViewModel({
    node, currentPath, onPathChange, onFileClick, showLabels, resetKey, projectName,
  });

  const visible = useFadeIn(scene);

  if (!scene) return null;

  return (
    <GalaxyCanvas visible={visible} canvasRef={refs.canvasRef} size={size} label={t('map.galaxyFolderAria')} handlers={handlers}>
      <ChartKeyboardControls label={t('map.galaxyKbdLabel')} items={starItems(scene, handlers.activateStar)} />
      <VizBreadcrumb items={breadcrumb.map((bc, i) => ({
        label: bc.label,
        onClick: i < breadcrumb.length - 1 ? () => handlers.goToPathIndex(bc.idx) : undefined,
      }))} />
      <GalaxyFolderOverlays tooltipRef={refs.tooltipRef} />
      <LevelInfoPanel levelInfo={levelInfo} />
    </GalaxyCanvas>
  );
}
