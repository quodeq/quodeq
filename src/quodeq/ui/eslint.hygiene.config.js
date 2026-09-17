// Hygiene ratchet: unused bindings, parameter counts, nesting depth and
// cyclomatic complexity.
//
// Separate from eslint.config.js (the i18n ratchet) and eslint.size.config.js
// (sizes) for the same reason those two are separate: each gate owns its
// rules and its baseline, so one gate's changes never move another's counts.
// Consumed by tools/check_hygiene.mjs with inline config disabled: the only
// way to grandfather a violation is tools/hygiene_baseline.json, which may
// only shrink.
import react from 'eslint-plugin-react';

export default [
  {
    files: ['src/**/*.js', 'src/**/*.jsx'],
    plugins: { react },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    rules: {
      // Marks components referenced only in JSX as used, so no-unused-vars
      // does not flag their imports.
      'react/jsx-uses-vars': 'error',
      // M-ANA-10: no dead code. Intentionally-unused bindings are spelled
      // with a leading underscore.
      'no-unused-vars': [
        'error',
        {
          vars: 'all',
          args: 'after-used',
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          ignoreRestSiblings: true,
          caughtErrors: 'none',
        },
      ],
      // M-MOD-4 (default 6): at most 6 parameters; pass one options object beyond that.
      'max-params': ['error', { max: 6 }],
      // M-ANA-3: blocks nest at most 4 deep; extract the inner branches into
      // named functions.
      'max-depth': ['error', { max: 4 }],
      // M-MOD-1 (default 15): cyclomatic complexity per function. Existing
      // offenders are grandfathered in the baseline; new ones split the
      // function.
      'complexity': ['error', { max: 15 }],
    },
  },
  {
    // M-TST-9: a plain reassignment of a global in a test survives the test.
    // vi.stubGlobal is undone after each test by `unstubGlobals: true` in
    // vitest.config.js; Object.defineProperty and `globalThis.x = ...` are not.
    files: ['src/**/*.test.jsx'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: "AssignmentExpression > MemberExpression.left[object.name=/^(globalThis|global|window)$/]",
          message: "Use vi.stubGlobal('<name>', value); plain global assignment leaks into later tests.",
        },
        {
          selector: "CallExpression[callee.object.name='Object'][callee.property.name='defineProperty'] > Identifier.arguments:first-child[name=/^(navigator|window|globalThis|document)$/]",
          message: "Use vi.stubGlobal('<name>', { ...<name>, prop: value }); defineProperty on a global leaks into later tests.",
        },
      ],
    },
  },
];
