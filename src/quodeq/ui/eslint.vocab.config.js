// Vocabulary-literal ratchet: bare run-state / job-status / severity / grade /
// exit-reason strings where the code branches on them. Mirrors
// tools/check_vocab_literals.py for the Python side. The fix is the frozen
// object in src/vocab/<name>.js: `status === RUN_STATE.RUNNING`.
//
// Consumed by tools/check_vocab.mjs with inline config disabled: the only
// way to grandfather a violation is tools/vocab_baseline.json, which may
// only shrink.
// One word list per vocabulary. Mirrors VOCABULARIES in
// tools/check_vocab_literals.py minus FileDoneStatus (no UI code reads
// file-done status) and Provider (the UI spells "custom" for the assistant
// mode too); tests/tools/test_vocab_gate_word_lists_match.py holds the two
// lists together. A word can sit in several lists; the same-vocabulary array
// rule matches per list.
const VOCABULARIES = {
  runState: [
    'pending', 'running', 'finalizing', 'done', 'failed', 'cancelled',
    'complete', 'completed', 'finished', 'in_progress', 'canceled', 'error', 'lost',
  ],
  jobStatus: ['running', 'done', 'failed', 'cancelled', 'lost'],
  exitReason: [
    'done', 'time_limit', 'deadline', 'failure_streak', 'cancelled', 'error',
    'stale_detected', 'stale_legacy_pid_dead', 'stale_legacy_no_pid',
  ],
  severity: ['critical', 'major', 'minor'],
  grade: ['Exemplary', 'Good', 'Adequate', 'Poor', 'Insufficient'],
  dimState: ['pending', 'running', 'done', 'incomplete'],
  findingType: ['violation', 'compliance'],
};
const WORDS = [...new Set(Object.values(VOCABULARIES).flat())];
const literal = (words) => `Literal[value=/^(${words.join('|')})$/]`;
const KEYS = ['status', 'state', 'severity', 'grade', 'exitReason', 'runState'];
const VALUE = literal(WORDS);
const KEY_RE = `/^(${KEYS.join('|')})$/`;
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
        // Write positions, symmetric with the reads above: `state = 'running'`,
        // `row.status = 'done'`, `const severity = 'critical'`.
        { selector: `AssignmentExpression[left.name=/^(${KEYS.join('|')})$/] > ${VALUE}.right`, message: MESSAGE },
        { selector: `AssignmentExpression[left.property.name=/^(${KEYS.join('|')})$/] > ${VALUE}.right`, message: MESSAGE },
        { selector: `VariableDeclarator[id.name=/^(${KEYS.join('|')})$/] > ${VALUE}.init`, message: MESSAGE },
        // Fallback of a vocabulary-named read: `row.status ?? 'running'`,
        // `state || 'done'` (the JS form of Python's `.get("state", "running")`).
        { selector: `LogicalExpression[operator=/^(\\?\\?|\\|\\|)$/][left.property.name=${KEY_RE}] > ${VALUE}.right`, message: MESSAGE },
        { selector: `LogicalExpression[operator=/^(\\?\\?|\\|\\|)$/][left.name=${KEY_RE}] > ${VALUE}.right`, message: MESSAGE },
        // An array holding two or more words of one vocabulary is a hand-copied
        // subset of it: `['done', 'failed']`. Matches from the second such word on.
        ...Object.values(VOCABULARIES).map((words) => ({
          selector: `ArrayExpression > ${literal(words)} ~ ${literal(words)}`,
          message: MESSAGE,
        })),
        // `'error' in payload` is a key test: the `in` operator is not in the
        // equality selector above, so its left operand is never flagged.
      ],
    },
  },
];
