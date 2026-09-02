export const EXT_DISPLAY_NAMES = {
  py: 'Python', js: 'JavaScript', ts: 'TypeScript', jsx: 'JSX', tsx: 'TSX',
  sh: 'Shell', bash: 'Shell', rb: 'Ruby', go: 'Go', rs: 'Rust',
  java: 'Java', kt: 'Kotlin', cs: 'C#', swift: 'Swift', dart: 'Dart',
  css: 'CSS', html: 'HTML', vue: 'Vue', php: 'PHP', c: 'C', cpp: 'C++',
};

/** Map a file extension to a human-readable language name. */
export function extDisplayName(ext) {
  return EXT_DISPLAY_NAMES[ext.toLowerCase()] || ext;
}
