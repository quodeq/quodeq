// These two rules are the only thing standing between the catalog and a
// slow drift back into hardcoded English, and both rest on heuristics. A
// heuristic that silently stops matching leaves the gate green while copy
// creeps back in, so pin both directions: what must be flagged, and what
// must stay quiet.
import { RuleTester } from 'eslint';
import plugin from './i18n_rules.mjs';

const jsx = new RuleTester({
  languageOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
});

const js = new RuleTester({
  languageOptions: { ecmaVersion: 'latest', sourceType: 'module' },
});

jsx.run('no-literal-visible-attrs', plugin.rules['no-literal-visible-attrs'], {
  valid: [
    // Already externalized.
    "const a = <button title={t('common.close')} />;",
    "const a = <input placeholder={t('projects.pathPlaceholder')} />;",
    // Structural attributes are not copy -- flagging these is what made
    // jsx-no-literals' own noAttributeStrings option unusable here.
    'const a = <div className="topbar-btn" role="dialog" />;',
    'const a = <path d="M1 12s4-8 11-8" />;',
    // Example values the user types, not text they read.
    'const a = <input placeholder="http://localhost:8000" />;',
    'const a = <input placeholder="git@github.com:org/repo.git" />;',
    // Non-literal values are someone else's problem.
    'const a = <img alt={label} />;',
  ],
  invalid: [
    { code: 'const a = <button title="Close window" />;', errors: 1 },
    { code: 'const a = <div aria-label="Open menu" />;', errors: 1 },
    { code: 'const a = <input placeholder="Search findings" />;', errors: 1 },
    { code: 'const a = <img alt="Score curve" />;', errors: 1 },
    // Both attributes on one element are two separate offences.
    { code: 'const a = <button title="Send" aria-label="Send" />;', errors: 2 },
  ],
});

js.run('no-prose-literals', plugin.rules['no-prose-literals'], {
  valid: [
    // Developer-facing sinks stay in English by design.
    "console.error('Failed to restore finding:', err);",
    "console.warn('[useProviderSettings] could not persist:', err);",
    "throw new Error('useEvalLog must be used inside <EvalLogProvider>');",
    "if (x) { throw new TypeError('expected a plain object here'); }",
    // Code-shaped strings.
    "const q = '(prefers-color-scheme: dark)';",
    "const c = 'qd-confirm-btn qd-confirm-btn--cancel';",
    "const s = '.app-shell__main-column > .dashboard';",
    "const f = '13px \"JetBrains Mono\", ui-monospace, monospace';",
    "const m = 'color-mix(in srgb, var(--color-sev-major-text) 22%, transparent)';",
    "const u = 'https://example.com/docs/getting-started';",
    // Too short or single-token to be a sentence.
    "const k = 'running';",
    "const k2 = 'time';",
    // Already externalized.
    "const msg = t('violations.deleteFailed');",
    // Object KEYS are identifiers, not copy.
    "const o = { 'some key here': 1 };",
    // Template literals: markup and class lists, including a BEM modifier
    // prefix left dangling before the interpolated half.
    'const c = `qd-confirm-btn qd-confirm-btn--confirm qd-confirm-btn--${variant}`;',
    'const c2 = `topbar-btn topbar-btn--${kind}`;',
    'const h = `<div style="color:${col}">${escapeHtml(name)}</div>`;',
    "console.error(`importProject failed (${status})`);",
  ],
  invalid: [
    { code: "const msg = 'Failed to restore finding. Please try again.';", errors: 1 },
    { code: "setError('An evaluation is already running. Cancel it or wait.');", errors: 1 },
    { code: "const t1 = 'Are you sure?';", errors: 1 },
    { code: "const o = { label: 'Import as copy' };", errors: 1 },
    { code: "const d = { title: 'Delete dismissed findings?', ok: 'Delete' };", errors: 1 },
    // A console call must not launder an unrelated nested string.
    { code: "console.log(format({ label: 'Choose an option here' }));", errors: 1 },
    // Prose split across an interpolation -- the surface jsx-no-literals and
    // the Literal handler both miss entirely.
    { code: 'const m = `Run an evaluation for ${name} to populate this page.`;', errors: 2 },
    { code: 'alert(`Failed to import project: ${err.message}`);', errors: 1 },
  ],
});

console.log('i18n_rules: all cases passed');
