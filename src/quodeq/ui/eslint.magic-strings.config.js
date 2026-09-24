// Magic-string ratchet: tools/magic_string_rules.mjs over the production UI.
// Mirrors tools/check_magic_strings.py for the Python side. Consumed by
// tools/check_magic_strings.mjs with inline config disabled: the only way to
// grandfather a violation is tools/magic_strings_baseline.json, which may
// only shrink.
import magicStringRules from './tools/magic_string_rules.mjs';

export default [
  {
    files: ['src/**/*.js', 'src/**/*.jsx'],
    ignores: [
      'src/vocab/**',
      'src/strings/**',
      'src/**/*.test.js',
      'src/**/*.test.jsx',
      'src/**/*.fixtures.js',
      'src/**/*.fixtures.jsx',
    ],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { 'magic-str': magicStringRules },
    rules: {
      'magic-str/compared-literal': 'error',
      'magic-str/repeated-literal': 'error',
    },
  },
];
