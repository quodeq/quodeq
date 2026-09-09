import { useEffect, useState } from 'react';
import { invalidateThemeColors } from '../core/galaxyCore.js';
import VizBreadcrumb from './VizBreadcrumb.jsx';
import MapLegend, { VizTooltipAnchor } from './MapLegend.jsx';
import { LevelInfoPanel } from './galaxyViewInfo.jsx';
import { useGalaxyViewModel } from './useGalaxyViewModel.js';
import { t } from '../../../../strings/index.js';

export default function GalaxyView({ dimensions, onNavigate, showLabels = true, setShowLabels, darkMode, resetKey = 0, projectName = '', standardTypes = {} }) {
  useEffect(() => { invalidateThemeColors(); }, [darkMode]);

  const { scene, size, canvasRef, tooltipRef, liveMsg, breadcrumb, levelInfo, handlers, startTransition, saveNav } = useGalaxyViewModel({
    dimensions, standardTypes, showLabels, resetKey, projectName, onNavigate,
  });

  const hasConstellations = scene?.constellations?.length > 0;
  const [visible, setVisible] = useState(false);
  useEffect(() => { if (hasConstellations) setVisible(true); }, [hasConstellations]);

  if (!scene) return null;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', opacity: visible ? 1 : 0, transition: 'opacity 0.4s ease' }}>
      <canvas ref={canvasRef} width={size.w} height={size.h}
        className="viz-focusable"
        style={{ width: '100%', height: '100%', display: 'block' }}
        onMouseMove={handlers.handleMouseMove} onMouseLeave={handlers.handleMouseLeave} onClick={handlers.handleClick}
        tabIndex={0}
        role="application"
        aria-label={t('map.galaxyAria')}
        onKeyDown={handlers.handleKeyDown}
        onFocus={handlers.handleFocus}
        onBlur={handlers.handleBlur} />
      <div aria-live="polite" aria-atomic="true" style={{
        position: 'absolute', width: 1, height: 1, padding: 0, margin: -1,
        overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap', border: 0,
      }}>{liveMsg}</div>
      <VizBreadcrumb items={breadcrumb.map((bc, i) => ({
        label: bc.label,
        onClick: i < breadcrumb.length - 1 ? () => {
          if (bc.action) { bc.action(); startTransition(true); saveNav(); }
          else handlers.goToDepth(bc.depth);
        } : undefined,
      }))} />
      <VizTooltipAnchor tooltipRef={tooltipRef} />
      <MapLegend />
      <LevelInfoPanel levelInfo={levelInfo} />
    </div>
  );
}
