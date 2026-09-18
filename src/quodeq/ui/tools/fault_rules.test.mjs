// The four fault-tolerance rules are heuristics over syntax, not types: they
// cannot prove a promise floats or a lookup misses. A heuristic that quietly
// stops matching leaves the ratchet green while the failure modes creep back,
// so pin both directions -- what must be flagged, and what must stay quiet.
import { RuleTester } from 'eslint';
import plugin from './fault_rules.mjs';

const js = new RuleTester({
  languageOptions: { ecmaVersion: 'latest', sourceType: 'module' },
});

js.run('swallowed-catch', plugin.rules['swallowed-catch'], {
  valid: [
    // Logged with a module prefix: the error reaches somebody.
    "try { f(); } catch (err) { console.warn('[m] f failed:', err); }",
    // Rethrown: the caller decides.
    'try { f(); } catch (err) { throw err; }',
    // Surfaced in the UI.
    'try { f(); } catch (err) { setError(err.message); }',
    // Not every logger is `console`. A warn/error/debug call on anything
    // counts as reaching somebody.
    "try { f(); } catch { log.warn('[m] failed'); }",
  ],
  invalid: [
    // Empty body, optional catch binding: the error is gone.
    { code: 'try { f(); } catch { }', errors: 1 },
    // A comment is not handling.
    { code: 'try { f(); } catch (e) { /* private mode */ }', errors: 1 },
    // Recovers, but drops the error entirely -- nothing to debug from.
    { code: 'try { f(); } catch (e) { setReady(false); }', errors: 1 },
    // An inner catch that logs its own error says nothing about the outer
    // one, which still drops `o` on the floor.
    {
      code: 'try { f(); } catch (o) { try { j(); } catch (n) { console.warn(n); } }',
      errors: 1,
    },
  ],
});

js.run('floating-promise', plugin.rules['floating-promise'], {
  valid: [
    'async function a() {} async function b() { await a(); }',
    'async function a() {} async function b() { return a(); }',
    // Deliberately discarded: `void` says so in the source.
    'async function a() {} async function b() { void a(); }',
    // Rejection is handled, so the statement is not floating.
    'async function a() {} async function b() { a().catch(console.warn); }',
    'f().then(g).catch(h);',
    // A prop or parameter that happens to share a name with a file-level
    // async function is a different binding. Resolve, do not string-match.
    'async function load() {} export function Row({ load }) { load(); }',
    'async function load() {} function Row(load) { load(); }',
  ],
  invalid: [
    { code: 'async function a() {} function b() { a(); }', errors: 1 },
    { code: 'f().then(g);', errors: 1 },
  ],
});

js.run('raw-storage-access', plugin.rules['raw-storage-access'], {
  valid: [
    // The approved wrapper, which handles private mode and quota errors.
    "import { readString } from '../adapters/storage.js'; readString('k');",
  ],
  invalid: [
    { code: "localStorage.getItem('k');", errors: 1 },
    { code: "sessionStorage.setItem('k','1');", errors: 1 },
    { code: "window.localStorage.removeItem('k');", errors: 1 },
  ],
});

js.run('unguarded-lookup-deref', plugin.rules['unguarded-lookup-deref'], {
  valid: [
    'const n = xs.find(p)?.name;',
    'const el = document.querySelector(s); if (el) el.focus();',
    'const m = s.match(re); const g = m && m[1];',
    // `.then`/`.catch`/`.finally` on a lookup result is promise plumbing,
    // not a dereference that can hit null.
    'api.get(url).then(r => r.data);',
    // `get` is only a nullable lookup on map-ish receivers. URLSearchParams
    // and Headers are the common counter-examples.
    "params.get('id').trim();",
    "res.headers.get('etag').length;",
  ],
  invalid: [
    { code: 'const n = xs.find(p).name;', errors: 1 },
    { code: 'document.querySelector(s).focus();', errors: 1 },
    { code: 'document.getElementById(i).value = 1;', errors: 1 },
    { code: 'const g = s.match(re)[1];', errors: 1 },
    { code: 'const v = map.get(k).value;', errors: 1 },
    { code: 'const v = nodesByIdCache.get(k).value;', errors: 1 },
  ],
});

console.log('fault_rules: all cases passed');
