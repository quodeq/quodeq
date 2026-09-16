import { useEffect, useState } from 'react';
import { DATA_THEME_ATTR, PREFERS_DARK_QUERY } from '../constants.js';

// Resolves whether the ACTIVE theme is dark by observing the applied
// DATA_THEME_ATTR attribute on <html> rather than re-reading settings state.
// useAppSettings owns the attribute; observing it keeps every consumer in
// sync no matter which code path applied the theme (TopBar toggle, Settings,
// initial paint). Attribute values: absent = daruma family in system mode
// (the OS preference decides); otherwise 'light' | 'dark' | '<family>-<mode>'.
function computeIsDark() {
  const attr = document.documentElement.getAttribute(DATA_THEME_ATTR);
  if (attr) return attr === 'dark' || attr.endsWith('-dark');
  return window.matchMedia(PREFERS_DARK_QUERY).matches;
}

export function useThemeIsDark() {
  const [isDark, setIsDark] = useState(computeIsDark);

  useEffect(() => {
    const update = () => setIsDark(computeIsDark());
    update(); // re-sync: covers any change between render and subscription
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: [DATA_THEME_ATTR],
    });
    const mql = window.matchMedia(PREFERS_DARK_QUERY);
    mql.addEventListener('change', update);
    return () => {
      observer.disconnect();
      mql.removeEventListener('change', update);
    };
  }, []);

  return isDark;
}
