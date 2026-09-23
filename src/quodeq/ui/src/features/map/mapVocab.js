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
