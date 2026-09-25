// Hygiene ratchet: unused bindings, parameter counts, nesting depth,
// cyclomatic complexity and JSDoc on exported API.
//
// Separate from eslint.config.js (the i18n ratchet) and eslint.size.config.js
// (sizes) for the same reason those two are separate: each gate owns its
// rules and its baseline, so one gate's changes never move another's counts.
// Consumed by tools/check_hygiene.mjs with inline config disabled: the only
// way to grandfather a violation is tools/hygiene_baseline.json, which may
// only shrink.
import react from 'eslint-plugin-react';
import jsdoc from 'eslint-plugin-jsdoc';
import { JSX_MODULE_LANGUAGE_OPTIONS, REACT_SETTINGS } from './tools/eslint_shared_config.mjs';

export default [
  {
    // M-ANA-5: every export in the shared layers carries a JSDoc block.
    //
    // Scoped to the layers other code imports across feature boundaries --
    // hooks, the API client, the utils and the feature-level hooks. Those are
    // read by callers who cannot see the implementation, so the block earns
    // its keep. Presentational components are deliberately out of scope: the
    // props are the contract there and a block per component would be noise.
    //
    // Landed at ZERO baseline entries and must stay there.
    files: [
      'src/hooks/**/*.js', 'src/hooks/**/*.jsx',
      'src/api/**/*.js', 'src/api/**/*.jsx',
      'src/utils/**/*.js', 'src/utils/**/*.jsx',
      'src/features/*/hooks/**/*.js', 'src/features/*/hooks/**/*.jsx',
    ],
    ignores: ['**/*.test.js', '**/*.test.jsx'],
    plugins: { jsdoc },
    languageOptions: JSX_MODULE_LANGUAGE_OPTIONS,
    rules: {
      'jsdoc/require-jsdoc': ['error', {
        publicOnly: true,
        require: {
          FunctionDeclaration: true,
          ArrowFunctionExpression: true,
          ClassDeclaration: true,
          FunctionExpression: false,
          MethodDefinition: false,
        },
        enableFixer: false,
      }],
    },
  },
  {
    files: ['src/**/*.js', 'src/**/*.jsx'],
    plugins: { react },
    languageOptions: JSX_MODULE_LANGUAGE_OPTIONS,
    settings: REACT_SETTINGS,
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
      // M-ANA-4: an inner binding that reuses an outer name makes the reader
      // check which one a line means. Rename the inner one.
      'no-shadow': 'error',
    },
  },
  {
    // M-TST-9: a plain reassignment of a global in a test survives the test.
    // vi.stubGlobal is undone after each test by `unstubGlobals: true` in
    // vitest.config.js; Object.defineProperty and `globalThis.x = ...` are not.
    files: ['src/**/*.test.jsx'],
    languageOptions: JSX_MODULE_LANGUAGE_OPTIONS,
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
