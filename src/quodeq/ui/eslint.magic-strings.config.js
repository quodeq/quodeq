// Magic-string ratchet: tools/magic_string_rules.mjs over the production UI.
// Mirrors tools/check_magic_strings.py for the Python side. Consumed by
// tools/check_magic_strings.mjs with inline config disabled: the only way to
// grandfather a violation is tools/magic_strings_baseline.json, which may
// only shrink.
import magicStringRules from './tools/magic_string_rules.mjs';
import { SRC_JS_JSX_BASE } from './tools/eslint_shared_config.mjs';

export default [
  {
    ...SRC_JS_JSX_BASE,
    plugins: { 'magic-str': magicStringRules },
    rules: {
      'magic-str/compared-literal': 'error',
      'magic-str/repeated-literal': 'error',
    },
  },
];
