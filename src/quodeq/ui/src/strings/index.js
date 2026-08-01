// User-visible string catalog. Every string a user reads belongs in
// en.json; adopting another language later means translating that one
// file. Keys are flat dot-paths ("feature.name"), values may contain
// {placeholder} slots filled via t(key, vars).
//
// Deliberately not i18next: no runtime locale switching or pluralization
// yet. That is a separate decision; this seam is what makes it cheap.
import en from './en.json' with { type: 'json' };

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
