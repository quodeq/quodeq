import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  extractPathCandidates,
  extractUrlCandidates,
  createUrlLinkProvider,
  createFileLinkProvider,
} from './terminalLinks.js';

test('relative path with slash', () => {
  const [c] = extractPathCandidates('editing src/quodeq/api/terminal_routes.py now');
  assert.equal(c.text, 'src/quodeq/api/terminal_routes.py');
  assert.equal(c.line, undefined);
});

test('dot-slash single segment', () => {
  const [c] = extractPathCandidates('run ./setup.sh');
  assert.equal(c.text, './setup.sh');
});

test('absolute path', () => {
  const [c] = extractPathCandidates('  File "/Users/x/proj/app.py", line 3');
  assert.equal(c.text, '/Users/x/proj/app.py');
});

test('home-relative single segment', () => {
  const [c] = extractPathCandidates('cat ~/notes.md');
  assert.equal(c.text, '~/notes.md');
});

test('pytest file:line:col suffix parsed, span excludes it', () => {
  const line = 'tests/api/test_x.py:42:7: AssertionError';
  const [c] = extractPathCandidates(line);
  assert.equal(c.text, 'tests/api/test_x.py');
  assert.equal(c.line, 42);
  assert.equal(c.col, 7);
  // span covers only the path, not :42:7
  assert.equal(line.slice(c.start, c.end), 'tests/api/test_x.py');
});

test('grep file:line suffix', () => {
  const [c] = extractPathCandidates('src/a/b.js:10:  const x = 1');
  assert.equal(c.text, 'src/a/b.js');
  assert.equal(c.line, 10);
  assert.equal(c.col, undefined);
});

test('trailing punctuation stripped', () => {
  const [c] = extractPathCandidates('see (src/a/b.js).');
  assert.equal(c.text, 'src/a/b.js');
  assert.equal('see (src/a/b.js).'.slice(c.start, c.end), 'src/a/b.js');
});

test('bare word without slash is not matched', () => {
  assert.deepEqual(extractPathCandidates('README and Makefile here'), []);
});

test('url is not captured as a path', () => {
  // https://... has slashes but the scheme host should not become a file link.
  // We do not assert zero here (defense is the backend existence check), but the
  // captured token must not be a plausible local file the backend would open.
  const cands = extractPathCandidates('visit https://example.com/a/b');
  for (const c of cands) {
    assert.ok(!c.text.startsWith('/'), `unexpected absolute token: ${c.text}`);
  }
});

test('multiple candidates on one line', () => {
  const cands = extractPathCandidates('mv src/a.js src/b.js');
  assert.equal(cands.length, 2);
  assert.deepEqual(cands.map((c) => c.text), ['src/a.js', 'src/b.js']);
});

test('empty line yields nothing', () => {
  assert.deepEqual(extractPathCandidates(''), []);
});

test('http url captured with correct span', () => {
  const line = 'open https://example.com/a/b?x=1 in browser';
  const [u] = extractUrlCandidates(line);
  assert.equal(u.text, 'https://example.com/a/b?x=1');
  assert.equal(line.slice(u.start, u.end), 'https://example.com/a/b?x=1');
});

test('url trailing paren/period stripped', () => {
  const [u] = extractUrlCandidates('(see http://localhost:7863/app).');
  assert.equal(u.text, 'http://localhost:7863/app');
});

test('no url yields nothing', () => {
  assert.deepEqual(extractUrlCandidates('just some text'), []);
});

test('url provider: 1-based range and cmd-gated activate', () => {
  const opened = [];
  const p = createUrlLinkProvider({
    readLine: () => 'x https://a.co/p',
    openUrl: (u) => opened.push(u),
  });
  let links;
  p.provideLinks(3, (l) => { links = l; });
  assert.equal(links.length, 1);
  // 'https://a.co/p' starts at index 2 -> start.x 3, y passthrough
  assert.deepEqual(links[0].range.start, { x: 3, y: 3 });
  // plain click does nothing; cmd-click opens
  links[0].activate({});
  assert.deepEqual(opened, []);
  links[0].activate({ metaKey: true });
  assert.deepEqual(opened, ['https://a.co/p']);
});

test('file provider: only existing files become links, opens abs+line', async () => {
  const opened = [];
  let resolveReq;
  const p = createFileLinkProvider({
    readLine: () => 'a src/real.js:5 and src/missing.js',
    resolvePaths: (paths) => {
      resolveReq = paths;
      return Promise.resolve([
        { input: 'src/real.js', abs: '/proj/src/real.js', exists: true },
        { input: 'src/missing.js', abs: '/proj/src/missing.js', exists: false },
      ]);
    },
    openFile: (abs, line, col) => opened.push([abs, line, col]),
  });
  const links = await new Promise((res) => p.provideLinks(2, res));
  assert.deepEqual(resolveReq, ['src/real.js', 'src/missing.js']);
  assert.equal(links.length, 1);
  assert.equal(links[0].text, 'src/real.js');
  links[0].activate({ ctrlKey: true });
  assert.deepEqual(opened, [['/proj/src/real.js', 5, undefined]]);
});

test('file provider: no candidates -> undefined, no backend call', async () => {
  let called = false;
  const p = createFileLinkProvider({
    readLine: () => 'nothing here',
    resolvePaths: () => { called = true; return Promise.resolve([]); },
    openFile: () => {},
  });
  const links = await new Promise((res) => p.provideLinks(1, res));
  assert.equal(links, undefined);
  assert.equal(called, false);
});

test('file provider: backend error -> undefined (no throw)', async () => {
  const p = createFileLinkProvider({
    readLine: () => 'edit src/a.js',
    resolvePaths: () => Promise.reject(new Error('boom')),
    openFile: () => {},
  });
  const links = await new Promise((res) => p.provideLinks(1, res));
  assert.equal(links, undefined);
});
