import { useState, useEffect } from 'react';
import { readString, writeString, STORAGE_FLAG_ON, STORAGE_FLAG_OFF } from '../../../adapters/storage.js';
import { useThemeIsDark } from '../../../hooks/useThemeIsDark.js';

const MAP_LABELS_KEY = 'quodeq-map-labels';
const MAP_DARK_KEY = 'quodeq-map-dark';

/** Show-labels + dark-mode viz prefs, persisted to storage. */
export function useMapDisplayPrefs() {
  const [showLabels, _setShowLabels] = useState(() => {
    const v = readString(MAP_LABELS_KEY);
    return v === null ? true : v === STORAGE_FLAG_ON;
  });
  const setShowLabels = (v) => { _setShowLabels(v); writeString(MAP_LABELS_KEY, v ? STORAGE_FLAG_ON : STORAGE_FLAG_OFF); };

  const appIsDark = useThemeIsDark();
  const [darkMode, _setDarkMode] = useState(() => {
    if (appIsDark) return true;
    return readString(MAP_DARK_KEY) === STORAGE_FLAG_ON;
  });
  const setDarkMode = (v) => { _setDarkMode(v); writeString(MAP_DARK_KEY, v ? STORAGE_FLAG_ON : STORAGE_FLAG_OFF); };
  // A dark app theme always forces dark viz; back on light, restore the
  // user's stored viz preference (defaulting to light when none is stored).
  useEffect(() => {
    if (appIsDark) { _setDarkMode(true); }
    else { _setDarkMode(readString(MAP_DARK_KEY) === STORAGE_FLAG_ON); }
  }, [appIsDark]);

  return { showLabels, setShowLabels, darkMode, setDarkMode };
}
