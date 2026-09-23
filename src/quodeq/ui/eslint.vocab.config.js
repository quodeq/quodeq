// Vocabulary-literal ratchet: bare run-state / job-status / severity / grade /
// exit-reason strings where the code branches on them. Mirrors
// tools/check_vocab_literals.py for the Python side. The fix is the frozen
// object in src/vocab/<name>.js: `status === RUN_STATE.RUNNING`.
//
// Consumed by tools/check_vocab.mjs with inline config disabled: the only
// way to grandfather a violation is tools/vocab_baseline.json, which may
// only shrink.
const WORDS = [
  'pending', 'running', 'finalizing', 'done', 'failed', 'cancelled',
  'complete', 'completed', 'finished', 'in_progress', 'canceled', 'lost',
  'time_limit', 'deadline', 'failure_streak', 'error',
  'stale_detected', 'stale_legacy_pid_dead', 'stale_legacy_no_pid',
  'critical', 'major', 'minor',
  'Exemplary', 'Good', 'Adequate', 'Poor', 'Insufficient',
  'ok', 'skipped', 'incomplete',
];
const KEYS = ['status', 'state', 'severity', 'grade', 'exitReason', 'runState'];
const VALUE = `Literal[value=/^(${WORDS.join('|')})$/]`;
const MESSAGE = 'Bare vocabulary literal; use the constant from src/vocab/*.js.';

export default [
  {
    files: ['src/**/*.js', 'src/**/*.jsx'],
    ignores: [
      'src/vocab/**',
      'src/strings/**',
      'src/**/*.test.js',
      'src/**/*.test.jsx',
      'src/**/*.fixtures.js',
      'src/**/*.fixtures.jsx',
    ],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      'no-restricted-syntax': [
        'error',
        { selector: `BinaryExpression[operator=/^(===|!==|==|!=)$/] > ${VALUE}`, message: MESSAGE },
        { selector: `SwitchCase > ${VALUE}.test`, message: MESSAGE },
        { selector: `NewExpression[callee.name='Set'] > ArrayExpression > ${VALUE}`, message: MESSAGE },
        { selector: `CallExpression[callee.property.name=/^(includes|has)$/] > ${VALUE}.arguments`, message: MESSAGE },
        { selector: `Property[key.name=/^(${KEYS.join('|')})$/] > ${VALUE}.value`, message: MESSAGE },
        { selector: `JSXAttribute[name.name=/^(${KEYS.join('|')})$/] > ${VALUE}`, message: MESSAGE },
      ],
    },
  },
];
