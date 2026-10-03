// The two magic-string rules are syntactic heuristics. Pin both directions,
// what must be flagged and what must stay quiet, so a rule that silently
// stops matching cannot leave the ratchet green.
import { RuleTester } from 'eslint';
import plugin from './magic_string_rules.mjs';

const tester = new RuleTester({
  languageOptions: { ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
});

tester.run('compared-literal', plugin.rules['compared-literal'], {
  valid: [
    "if (typeof x === 'string') f();",
    "if (mode === MODE.GALAXY) f();",
    "if (x === ', ') f();",
    "if (status === 'running') f();",
    "const MODE_GALAXY = 'galaxy';",
    "if ('user' in msg) f();",
  ],
  invalid: [
    { code: "if (mode === 'galaxy') f();", errors: [{ messageId: 'bare' }] },
    { code: "if ('asc' !== dir) f();", errors: [{ messageId: 'bare' }] },
    { code: "switch (k) { case 'Enter': f(); }", errors: [{ messageId: 'bare' }] },
    { code: "if (['user', 'assistant'].includes(role)) f();", errors: [{ messageId: 'bare' }, { messageId: 'bare' }] },
  ],
});

tester.run('repeated-literal', plugin.rules['repeated-literal'], {
  valid: [
    "f('dark'); g('dark');",
    "const THEMES = ['dark', 'dark', 'dark'];",
    "f({ theme: 'dark' }); g({ theme: 'dark' }); h({ theme: 'dark' });",
    "a['dark']; b['dark']; c['dark'];",
    "t('dark'); t('dark'); t('dark');",
    "const x = <A kind='dark' />; const y = <B kind='dark' />; const z = <C kind={on ? 'dark' : 'x'} />;",
    "import a from 'dark'; import b from 'dark2'; export * from 'dark3';",
  ],
  invalid: [
    { code: "f('dark'); g('dark'); h('dark');", errors: [{ messageId: 'repeated' }] },
    { code: "function a() { return x ? 'dark' : y ? 'dark' : 'dark'; }", errors: [{ messageId: 'repeated' }] },
  ],
});
