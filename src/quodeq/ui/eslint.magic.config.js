// Magic-number ratchet: unexplained numeric literals in production UI code.
//
// Separate from eslint.hygiene.config.js for the same reason the strings and
// size gates are separate: each gate owns its rules and its baseline, so one
// gate's changes never move another's counts. Consumed by tools/check_magic.mjs
// with inline config disabled: the only way to grandfather a violation is
// tools/magic_baseline.json, which may only shrink.
//
// M-MDF-1 (maintainability): a literal with meaning gets a name where it is
// used. One module: `const UPPER_SNAKE = value; // why this value`. Shared
// within a feature: that feature's constants-bearing module. App-wide keys,
// events, queries and breakpoints: src/constants.js. Unit conversions:
// src/utils/time.js. See CONTRIBUTING.md, Code Style.
//
// Ignored values are self-describing: -1/0/1/2 (sentinels, unit steps) —
// the floor. The score scale, percent and time unit factors (10, 24, 60,
// 100, 1000) are named constants, not ignored: every other literal in
// production UI code names a home rather than being grandfathered here.
// Tests and fixtures are excluded: there the literal is the expected value,
// which is the contract under test.
import { JSX_MODULE_LANGUAGE_OPTIONS } from './tools/eslint_shared_config.mjs';

export default [
  {
    files: ['src/**/*.js', 'src/**/*.jsx'],
    ignores: [
      'src/**/*.test.js',
      'src/**/*.test.jsx',
      'src/**/*.fixtures.js',
      'src/**/*.fixtures.jsx',
    ],
    languageOptions: JSX_MODULE_LANGUAGE_OPTIONS,
    rules: {
      'no-magic-numbers': [
        'error',
        {
          ignore: [-1, 0, 1, 2],
          ignoreArrayIndexes: true,
          ignoreDefaultValues: true,
          ignoreClassFieldInitialValues: true,
          // Object literals are usually already the named form
          // ({ padding: 12 } reads as a name/value pair).
          detectObjects: false,
          enforceConst: false,
        },
      ],
    },
  },
];
