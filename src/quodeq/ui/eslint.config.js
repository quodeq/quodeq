// Single-purpose ESLint config: the i18n string ratchet. This is NOT a
// general lint setup; the only rule is react/jsx-no-literals, consumed by
// tools/check_strings.mjs against a grandfathered baseline. Add general
// linting elsewhere, not here, or the ratchet counts drift.
import react from 'eslint-plugin-react';
import i18n from './tools/i18n_rules.mjs';

// Files whose English is addressed to a model or to a file format, not to a
// person: LLM prompt scaffolding and the exported-report layout. Translating
// these would change what the assistant is told to do, so they are excluded
// rather than grandfathered -- a baseline entry would read as debt.
const NOT_USER_FACING = [
  'src/utils/planConstants.js',
  'src/utils/planBuilder.js',
  'src/utils/planTextBuilders.js',
  'src/utils/reportBuilder.js',
  'src/utils/reportBuilder/shared.js',
  'src/utils/reportBuilder/dimensionSummary.js',
  'src/utils/reportBuilder/runBuilders.js',
  'src/utils/reportBuilder/principleBuilder.js',
  'src/utils/reportBuilder/fileBuilder.js',
];

export default [
  {
    files: ['src/**/*.jsx'],
    ignores: ['**/*.test.jsx'],
    plugins: { react, i18n },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    rules: {
      'react/jsx-no-literals': [
        'error',
        {
          // Also flag {'text'} expression literals, not just bare text nodes.
          noStrings: true,
          // Props stay out of scope here. noAttributeStrings cannot help:
          // it is inert while ignoreProps is on, and enabling both flags
          // ~6.7k className/role/svg-path strings because the rule cannot
          // tell a visible attribute from a structural one. Visible
          // attributes are covered by i18n/no-literal-visible-attrs instead.
          ignoreProps: true,
          noAttributeStrings: false,
          // Pure punctuation/symbol glyphs are not translatable text.
          allowedStrings: [' ', '×', '·', '•', '…', ':', '(', ')', '[', ']', '/', ',', '-', '%', '—', '‹', '›', '→', '@', '↑', '↓', '+', '▸', '▶', '✓', '✕', '↻', 'Δ', '⟳', '▾', '?', '.', '←', '>_', '--'],
        },
      ],
      'i18n/no-literal-visible-attrs': 'error',
      // .jsx carries two blind spots jsx-no-literals cannot see: prose in
      // template literals, and prose in props (ignoreProps skips those, and
      // the visible-attribute rule above only covers title/placeholder/
      // aria-label/alt on DOM elements, not `label=` on a component).
      // Enabling this needed the structural-position filters in
      // tools/i18n_rules.mjs first -- by shape alone, "chip small" is
      // indistinguishable from copy.
      'i18n/no-prose-literals': 'error',
    },
  },
  {
    // Prose living in plain-JS logic: toasts, confirm dialogs, fetch-error
    // fallbacks. Separate block because jsx-no-literals has nothing to say
    // about .js and would only add noise here.
    files: ['src/**/*.js'],
    ignores: ['**/*.test.js', ...NOT_USER_FACING],
    plugins: { i18n },
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module' },
    rules: { 'i18n/no-prose-literals': 'error' },
  },
];
