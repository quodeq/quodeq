import { useEffect, useMemo, useState } from 'react';
import { invalidateThemeColors, LEGEND_ITEMS } from '../core/galaxyCore.js';
import VizBreadcrumb from './VizBreadcrumb.jsx';
import { buildLevelInfo } from './galaxyFolderScene.js';
import { createEventHandlers } from './galaxyFolderEvents.js';
import { useGalaxyFolderNav } from './useGalaxyFolderNav.js';
import { useGalaxyFolderCamera } from './useGalaxyFolderCamera.js';
import GalaxyFolderPanel from './GalaxyFolderPanel.jsx';
import { t } from '../../../../strings/index.js';

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
      <div
        ref={tooltipRef}
        style={{ position: 'fixed', display: 'none', background: 'color-mix(in srgb, var(--color-surface) 92%, transparent)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '10px 14px', pointerEvents: 'none', fontSize: 12, zIndex: 10, boxShadow: '0 4px 20px rgba(0,0,0,0.3)', backdropFilter: 'blur(8px)', minWidth: 140 }}
      />
      <div style={{ position: 'absolute', bottom: 8, left: 12, display: 'flex', gap: 14, fontSize: 11, color: 'var(--color-text-muted)', zIndex: 2 }}>
        {LEGEND_ITEMS.map(({ color, label }) => (
          <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />{label}
          </span>
        ))}
      </div>
    </>
  );
}

export default function GalaxyFolderView({ node, currentPath = '', onPathChange, onFileClick, onNavigate, showLabels = true, setShowLabels, darkMode, resetKey = 0, projectName = '' }) {
  useEffect(() => { invalidateThemeColors(); }, [darkMode]);

  const { refs, scene, size, handlers, breadcrumb, levelInfo } = useGalaxyFolderViewModel({
    node, currentPath, onPathChange, onFileClick, showLabels, resetKey, projectName,
  });

  // Fade in
  const [visible, setVisible] = useState(false);
  useEffect(() => { if (scene) setVisible(true); }, [scene]);

  if (!scene) return null;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', opacity: visible ? 1 : 0, transition: 'opacity 0.4s ease' }}>
      <canvas
        className="viz-focusable"
        ref={refs.canvasRef}
        width={size.w}
        height={size.h}
        style={{ width: '100%', height: '100%', display: 'block' }}
        tabIndex={0}
        role="application"
        aria-label={t('map.galaxyFolderAria')}
        onMouseMove={handlers.handleMouseMove}
        onMouseLeave={handlers.handleMouseLeave}
        onClick={handlers.handleClick}
        onKeyDown={handlers.handleKeyDown}
      />
      <VizBreadcrumb items={breadcrumb.map((bc, i) => ({
        label: bc.label,
        onClick: i < breadcrumb.length - 1 ? () => handlers.goToPathIndex(bc.idx) : undefined,
      }))} />
      <GalaxyFolderOverlays tooltipRef={refs.tooltipRef} />
      <GalaxyFolderPanel levelInfo={levelInfo} />
    </div>
  );
}
