// Theme mode/palette-family vocab. No Python mirror: a purely presentational
// choice persisted under cc-theme-mode/cc-theme-family (hooks/useAppSettings.js)
// and resolved onto the DATA_THEME_ATTR by utils/themeResolver.js.
export const THEME_MODE = Object.freeze({ SYSTEM: 'system', LIGHT: 'light', DARK: 'dark' });
export const THEME_FAMILY = Object.freeze({
  DARUMA: 'daruma', NEO: 'neo', GALADRIEL: 'galadriel', IFRIT: 'ifrit', DECKARD: 'deckard',
});
