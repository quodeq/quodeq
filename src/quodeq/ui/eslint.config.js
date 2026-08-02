// Single-purpose ESLint config: the i18n string ratchet. This is NOT a
// general lint setup; the only rule is react/jsx-no-literals, consumed by
// tools/check_strings.mjs against a grandfathered baseline. Add general
// linting elsewhere, not here, or the ratchet counts drift.
import react from 'eslint-plugin-react';

export default [
  {
    files: ['src/**/*.jsx'],
    ignores: ['**/*.test.jsx'],
    plugins: { react },
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
          // Props (className etc.) stay out of scope for now; visible
          // attribute text (title/placeholder/aria-label) is a later
          // tightening once the text-node sweep lands.
          ignoreProps: true,
          noAttributeStrings: false,
          // Pure punctuation/symbol glyphs are not translatable text.
          allowedStrings: [' ', '×', '·', '•', '…', ':', '(', ')', '[', ']', '/', ',', '-', '%', '—', '‹', '›', '→', '@', '↑', '+', '▸', '✓', '✕', '↻', 'Δ', '⟳', '▾', '?', '.', '←'],
        },
      ],
    },
  },
];
