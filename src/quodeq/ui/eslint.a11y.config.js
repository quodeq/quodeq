// Accessibility ratchet: eslint-plugin-jsx-a11y's recommended rules over the
// production UI (U-ACC-1..4). Separate config so this gate owns its rules and
// its baseline. Consumed by tools/check_a11y.mjs with inline config disabled:
// the only way to grandfather a violation is tools/a11y_baseline.json, which
// may only shrink. Tests and fixtures are excluded: test markup asserts on
// behaviour, it is not shipped UI.
//
// no-autofocus is off: the dialogs move focus deliberately on open, which is
// the WAI-ARIA dialog pattern, and the rule cannot tell that apart from a
// stray autoFocus on a page field.
import jsxA11y from 'eslint-plugin-jsx-a11y';

export default [
  {
    files: ['src/**/*.jsx'],
    ignores: ['src/**/*.test.jsx', 'src/**/*.fixtures.jsx'],
    plugins: { 'jsx-a11y': jsxA11y },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      'jsx-a11y/no-autofocus': 'off',
      // A focusable separator is the WAI-ARIA window-splitter pattern (the
      // side-pane, drawer and standards-tree dividers resize with the arrow
      // keys); the plugin classifies the role as non-interactive regardless.
      'jsx-a11y/no-noninteractive-tabindex': [
        'error',
        { tags: [], roles: ['tabpanel', 'separator'], allowExpressionValues: true },
      ],
    },
  },
];
