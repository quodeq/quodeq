// Single-purpose ESLint config: the size ratchet (300-line files, 50-line
// functions). Separate from eslint.config.js (the i18n ratchet), whose
// header forbids adding unrelated rules there. Consumed by
// tools/check_size_grandfather.mjs against the grandfather list in
// tools/size_grandfather.mjs.
//
// Run with `--no-inline-config` (see package.json's lint:size script): this
// config only registers the two size rules, so a leftover
// `/* eslint-disable react-hooks/exhaustive-deps */` comment (a rule this
// config doesn't know about) would otherwise fail the run with "Definition
// for rule ... was not found". It also means a size violation cannot be
// waived with an inline comment -- grandfathering only happens through the
// reviewed list below, which is the point of a ratchet.
import { SIZE_GRANDFATHER } from './tools/size_grandfather.mjs';

const SIZE_RULES = {
  'max-lines': ['error', { max: 300, skipBlankLines: false }],
  'max-lines-per-function': ['error', { max: 50 }],
};

export default [
  {
    files: ['src/**/*.js', 'src/**/*.jsx'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: SIZE_RULES,
  },
  // Grandfathered offenders: downgrade both rules so today's violations
  // don't fail the build. New violations in these files still slip through
  // until they are split -- the count-lock in check_size_grandfather.mjs is
  // what stops the list from growing; burn it down by splitting a file and
  // removing its entry. `files` may not be an empty array in flat config,
  // so this block is only added once there is at least one entry.
  ...(SIZE_GRANDFATHER.length > 0
    ? [{ files: SIZE_GRANDFATHER, rules: { 'max-lines': 'off', 'max-lines-per-function': 'off' } }]
    : []),
];
