// Hover/click hit-test target kinds for the two galaxy scenes. Kept off
// galaxyCore.js because most galaxy component tests fully mock that module;
// these are plain string constants with no rendering dependency, so they
// don't need to live there.

// The folder galaxy's hit-test result kind: galaxyFolderDraw.js and
// galaxyFolderEvents.js build these, galaxyFolderClickHandlers.js and
// galaxyFolderTooltip.js read them back.
export const HIT_TARGET_TYPE = Object.freeze({ FOLDER: 'folder', FILE: 'file' });

// The dimension-galaxy view's own hover-target kind (a different star scene
// from the folder galaxy above): galaxyViewDraw.js's hit test builds these,
// galaxyViewEvents.js reads them back.
export const GALAXY_VIEW_HOVER_TYPE = Object.freeze({ DIM: 'dim', PRIN: 'prin' });
