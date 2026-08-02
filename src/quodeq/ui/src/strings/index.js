// User-visible string catalog. Every string a user reads belongs in
// en.json; adopting another language later means translating that one
// file. Keys are flat dot-paths ("feature.name"), values may contain
// {placeholder} slots filled via t(key, vars).
//
// Deliberately not i18next: no runtime locale switching or pluralization
// yet. That is a separate decision; this seam is what makes it cheap.
import en from './en.json' with { type: 'json' };

/**
 * BCP-47 tag for everything Intl formats: dates, times, numbers.
 *
 * Paired with the catalog above, deliberately. Call sites used to pass
 * `undefined`, which means "the browser's locale" -- so a Dutch machine
 * running the English UI got Dutch dates next to English copy, and adding a
 * locale would not have changed them at all. One tag, one place.
 *
 * 'en-GB' rather than 'en' is also deliberate: the app renders dates
 * day-month-year ("25 Mar 2026"), which is what this tag encodes. Plain 'en'
 * resolves to US ordering and would silently reformat every date in the
 * product.
 */
export const LOCALE = 'en-GB';

export function t(key, vars) {
  const template = en[key];
  if (template === undefined) {
    if (import.meta.env?.DEV) console.warn(`missing string key: ${key}`);
    return key;
  }
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    Object.hasOwn(vars, name) ? String(vars[name]) : match,
  );
}
