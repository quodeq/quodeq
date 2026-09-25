// Fault-tolerance ratchet: tools/fault_rules.mjs over the production UI
// (R-FT-1..3). Consumed by tools/check_fault.mjs with inline config disabled:
// the only way to grandfather a violation is tools/fault_baseline.json, which
// may only shrink. src/adapters/storage.js is the approved web-storage
// wrapper -- the one place raw localStorage access is correct.
import faultRules from './tools/fault_rules.mjs';
import { JSX_MODULE_LANGUAGE_OPTIONS } from './tools/eslint_shared_config.mjs';

export default [
  {
    files: ['src/**/*.js', 'src/**/*.jsx'],
    ignores: ['src/**/*.test.js', 'src/**/*.test.jsx', 'src/**/*.fixtures.js', 'src/**/*.fixtures.jsx'],
    plugins: { fault: faultRules },
    languageOptions: JSX_MODULE_LANGUAGE_OPTIONS,
    rules: {
      'fault/swallowed-catch': 'error',
      'fault/floating-promise': 'error',
      'fault/raw-storage-access': 'error',
      'fault/unguarded-lookup-deref': 'error',
    },
  },
  { files: ['src/adapters/storage.js'], rules: { 'fault/raw-storage-access': 'off' } },
];
