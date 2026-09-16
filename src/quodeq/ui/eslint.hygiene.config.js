// Hygiene ratchet: unused bindings and parameter counts.
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
      // M-MOD-4: at most 5 parameters; pass one options object beyond that.
      'max-params': ['error', { max: 5 }],
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
