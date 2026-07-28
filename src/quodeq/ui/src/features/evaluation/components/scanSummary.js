/**
 * Pure helpers for the setup card's "detected files" line and time-budget
 * chips. No React — node-testable.
 */

// Extension → display language for the detected-files line. Only analyzable
// extensions (mirrors _CODE_EXTENSIONS in services/_fs_scan.py); everything
// else in scanData.languages (json, md, …) is noise for this line.
const EXT_LANGUAGE = {
  py: 'python', pyx: 'python',
  ts: 'typescript', tsx: 'typescript',
  js: 'javascript', jsx: 'javascript',
  java: 'java',
  kt: 'kotlin', kts: 'kotlin',
  swift: 'swift',
  m: 'objective-c',
  go: 'go',
  rs: 'rust',
  rb: 'ruby',
  php: 'php',
  sh: 'bash', bash: 'bash',
  cs: 'c#',
  cpp: 'c++',
  c: 'c', h: 'c',
  scala: 'scala',
  dart: 'dart',
  ex: 'elixir', exs: 'elixir',
  r: 'r',
  hs: 'haskell', lhs: 'haskell',
  lua: 'lua',
  jl: 'julia',
  zig: 'zig',
  ml: 'ocaml', mli: 'ocaml',
  cr: 'crystal',
  pl: 'perl', pm: 'perl',
};

/**
 * Top source languages from scanData.languages (extension → count),
 * aggregated per language, sorted by count desc.
 * @returns {Array<{name:string, count:number}>}
 */
export function detectedLanguages(languages, limit = 4) {
  const byLang = new Map();
  for (const [ext, count] of Object.entries(languages || {})) {
    const name = EXT_LANGUAGE[ext.toLowerCase()];
    if (!name || !(count > 0)) continue;
    byLang.set(name, (byLang.get(name) || 0) + count);
  }
  return [...byLang.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

/** Preset total run time budgets, in seconds. 0 = no limit. */
export const BUDGET_CHOICES_S = [300, 600, 1200, 1800, 0];

/** "10:00" for seconds, "no limit" for 0/negative. */
export function formatBudgetLabel(seconds) {
  if (!(seconds > 0)) return 'no limit';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}
