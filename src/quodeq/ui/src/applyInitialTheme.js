import { resolveDataTheme } from './utils/themeResolver.js';
import { DATA_THEME_ATTR, PREFERS_DARK_QUERY } from './constants.js';
import { THEME_MODE, THEME_FAMILY } from './vocab/theme.js';

const LS_THEME = 'cc-theme';
const LS_THEME_MODE = 'cc-theme-mode';
const LS_THEME_FAMILY = 'cc-theme-family';

// Retired family: never a THEME_FAMILY member (useAppSettings.js's
// FAMILY_RENAMES folds it into daruma), but the pre-boot migration below
// still has to route old midnight/horizon selections through it exactly as
// it always has, so it needs a name of its own.
const LEGACY_FAMILY_FLYNN = 'flynn';

const LEGACY_THEME_MAP = {
  system: [THEME_MODE.SYSTEM, THEME_FAMILY.DARUMA],
  light: [THEME_MODE.LIGHT, THEME_FAMILY.DARUMA],
  dark: [THEME_MODE.DARK, THEME_FAMILY.DARUMA],
  ember: [THEME_MODE.DARK, THEME_FAMILY.IFRIT],
  forest: [THEME_MODE.LIGHT, THEME_FAMILY.GALADRIEL],
  midnight: [THEME_MODE.DARK, LEGACY_FAMILY_FLYNN],
  slate: [THEME_MODE.LIGHT, THEME_FAMILY.DARUMA],
  horizon: [THEME_MODE.LIGHT, LEGACY_FAMILY_FLYNN],
};

const LEGACY_FAMILY_MAP = {
  default: THEME_FAMILY.DARUMA,
  midnight: LEGACY_FAMILY_FLYNN,
  forest: THEME_FAMILY.GALADRIEL,
  ember: THEME_FAMILY.IFRIT,
  cyber: THEME_FAMILY.DECKARD,
};

/**
 * Applies the persisted (or default) theme to the document before first
 * paint, migrating legacy storage keys/values on the way. Throws if
 * `storage` or `mediaQuery` throws (e.g. storage access blocked); the
 * caller is responsible for treating this as a fault-isolation boundary.
 */
export function applyInitialTheme(storage = localStorage, mediaQuery = window.matchMedia) {
  const oldTheme = storage.getItem(LS_THEME);
  if (oldTheme !== null) {
    const [m, f] = LEGACY_THEME_MAP[oldTheme] || [THEME_MODE.SYSTEM, THEME_FAMILY.DARUMA];
    storage.setItem(LS_THEME_MODE, m);
    storage.setItem(LS_THEME_FAMILY, f);
    storage.removeItem(LS_THEME);
  }
  const oldFamily = storage.getItem(LS_THEME_FAMILY);
  if (oldFamily && LEGACY_FAMILY_MAP[oldFamily]) {
    storage.setItem(LS_THEME_FAMILY, LEGACY_FAMILY_MAP[oldFamily]);
  }
  const mode = storage.getItem(LS_THEME_MODE) || THEME_MODE.SYSTEM;
  const family = storage.getItem(LS_THEME_FAMILY) || THEME_FAMILY.DARUMA;
  const prefersDark = mediaQuery(PREFERS_DARK_QUERY).matches;
  const dataTheme = resolveDataTheme(mode, family, prefersDark);
  if (dataTheme !== null) {
    document.documentElement.setAttribute(DATA_THEME_ATTR, dataTheme);
  }
}
