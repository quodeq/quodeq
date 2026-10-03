// The map's colour/size mode: the `viewMode` nav param, MapPage's toggle and
// the switches in viz/core/mapColors.js. The toggle offers health and
// violations; 'compliance' has no button but mapColors still renders it when
// a link carries it. Not the finding type, though it shares a word with it.
export const MAP_VIEW_MODE = Object.freeze({ HEALTH: 'health', VIOLATIONS: 'violations', COMPLIANCE: 'compliance' });

// The modes MapPage's toggle offers, in display order.
export const VIEW_MODES = [
  { id: MAP_VIEW_MODE.HEALTH, label: 'Health' },
  { id: MAP_VIEW_MODE.VIOLATIONS, label: 'Violations' },
];

// The map's three layout engines (the `vizStyle` nav param): MapPage's
// toggle and useMapPageState's nav-param default.
export const VIZ_STYLE = Object.freeze({ ZOOMPACK: 'zoompack', GALAXY: 'galaxy', RISKMATRIX: 'riskmatrix' });

// Sub-mode of VIZ_STYLE.GALAXY (the `galaxyMode` nav param): grouped by
// folder structure or by standard/dimension.
export const GALAXY_MODE = Object.freeze({ FILESYSTEM: 'filesystem', STANDARDS: 'standards' });
