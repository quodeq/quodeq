import { useEffect } from 'react';
import { invalidateThemeColors } from '../core/galaxyCore.js';
import VizBreadcrumb from './VizBreadcrumb.jsx';
import MapLegend, { VizTooltipAnchor } from './MapLegend.jsx';
import { LevelInfoPanel } from './galaxyViewInfo.jsx';
import GalaxyCanvas, { useFadeIn } from './GalaxyCanvas.jsx';
import { useGalaxyViewModel } from './useGalaxyViewModel.js';
import { t } from '../../../../strings/index.js';

export default function GalaxyView({ dimensions, onNavigate, showLabels = true, darkMode, resetKey = 0, projectName = '', standardTypes = {} }) {
  useEffect(() => { invalidateThemeColors(); }, [darkMode]);

  const { scene, size, canvasRef, tooltipRef, liveMsg, breadcrumb, levelInfo, handlers, startTransition, saveNav } = useGalaxyViewModel({
    dimensions, standardTypes, showLabels, resetKey, projectName, onNavigate,
  });

  const hasConstellations = scene?.constellations?.length > 0;
  const visible = useFadeIn(hasConstellations);

  if (!scene) return null;

  return (
    <GalaxyCanvas visible={visible} canvasRef={canvasRef} size={size} label={t('map.galaxyAria')} handlers={handlers}>
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
    </GalaxyCanvas>
  );
}
