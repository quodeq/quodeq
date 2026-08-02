#!/usr/bin/env node
// One-shot migration: HelpSections.jsx -> per-locale markdown in
// src/features/help/content/en/. Kept in tools/ for provenance: it documents
// exactly how the English content was derived, so the conversion can be
// re-audited without diffing 750 lines of deleted JSX by eye.
//
// Not a general JSX parser. It handles precisely the constructs HelpSections
// used, and throws on anything it does not recognise rather than silently
// dropping content -- a dropped sentence is invisible in the rendered page,
// so the loud failure is the point.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const UI_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = path.join(UI_ROOT, 'src/features/help/components/HelpSections.jsx');
const OUT_DIR = path.join(UI_ROOT, 'src/features/help/content/en');

// Section export name -> file slug (mirrors HelpPage's SECTION ids).
const SLUGS = {
  Philosophy: 'philosophy', GettingStarted: 'getting-started', Projects: 'projects',
  SharedRepository: 'shared-repo', Providers: 'providers', Evaluations: 'evaluations',
  Overview: 'overview', Dimensions: 'dimensions', Violations: 'violations',
  CodeMap: 'map', History: 'history', GradeFormula: 'grade-formula',
  Standards: 'standards', Assistant: 'assistant', Terminal: 'terminal',
  Settings: 'settings', CommandLine: 'cli',
};

const ENTITIES = {
  '&#xB2;': '\u00b2', '&#x2082;': '\u2082', '&middot;': '\u00b7', '&apos;': "'",
  '&quot;': '"', '&rsquo;': '\u2019', '&lsquo;': '\u2018', '&ldquo;': '\u201c',
  '&rdquo;': '\u201d', '&hellip;': '\u2026', '&mdash;': '\u2014', '&ndash;': '\u2013',
  '&nbsp;': ' ', '&gt;': '>', '&lt;': '<', '&amp;': '&',
};

function decode(s) {
  return s.replace(/&#?\w+;/g, (m) => {
    if (m in ENTITIES) return ENTITIES[m];
    throw new Error(`unknown entity ${m}`);
  });
}

// Inline JSX -> inline markdown. Escapes markdown-significant characters that
// appear literally in the prose so a round-trip renders identically.
function inline(s) {
  let out = decode(s);
  out = out.replace(/<>|<\/>/g, '');            // bare fragments carry no meaning
  out = out.replace(/\{ICON_EYE_ON\}/g, '`icon:eye`');
  // Severity badges: the label comes from the catalog at render time, so the
  // markdown only carries which badge, never its text.
  out = out.replace(/<span className="severity-tag (\w+)">[^<]*<\/span>/g, (_, kind) => `\`tag:${kind}\``);
  out = out.replace(/<strong>([\s\S]*?)<\/strong>/g, (_, x) => `**${inline(x)}**`);
  out = out.replace(/<em>([\s\S]*?)<\/em>/g, (_, x) => `*${inline(x)}*`);
  // A code span whose content contains a backtick (the keyboard shortcuts do)
  // needs a longer fence and padding, or markdown ends the span early and the
  // stray backtick leaks into the rendered text.
  out = out.replace(/<code>([\s\S]*?)<\/code>/g, (_, x) => {
    const body = decode(x);
    if (!body.includes('`')) return `\`${body}\``;
    const longest = Math.max(...[...body.matchAll(/`+/g)].map((m) => m[0].length));
    const fence = '`'.repeat(longest + 1);
    return `${fence} ${body} ${fence}`;
  });
  out = out.replace(/\s+/g, ' ').trim();
  // Anything still tag-shaped is a construct this converter does not know, so
  // fail loudly. A closing tag or a capitalised component name are the two
  // reliable tells; a bare `<repo>` is a CLI placeholder in prose, not markup.
  const bare = out.replace(/`[^`]*`/g, '');
  if (/<\/|<[A-Z]/.test(bare)) throw new Error(`unhandled inline tag in: ${out.slice(0, 90)}`);
  if (/[{}]/.test(bare)) throw new Error(`unhandled expression in: ${out.slice(0, 90)}`);
  // Escape the literal angle brackets that survive, so markdown renders them
  // as text instead of swallowing them as raw HTML.
  return out.replace(/<(?![^`]*`)/g, '&lt;').replace(/(?<!`[^`]*)>/g, '&gt;');
}

// Parse the `rows={[...]}` array of a <KeyTable>. A cell is either a quoted
// string or a JSX fragment (`<><code>x</code></>`), so this scans rather than
// pattern-matches: a regex that assumed two quoted strings silently skipped
// every row whose value was markup.
function scanCells(row) {
  const cells = [];
  let i = 0;
  while (i < row.length) {
    while (i < row.length && /[\s,]/.test(row[i])) i++;
    if (i >= row.length) break;
    const ch = row[i];
    if (ch === "'" || ch === '"') {
      let j = i + 1, buf = '';
      while (j < row.length && row[j] !== ch) {
        if (row[j] === '\\') { buf += row[j + 1]; j += 2; continue; }
        buf += row[j++];
      }
      cells.push(buf); i = j + 1;
    } else if (ch === '<') {
      // Consume to the end of the top-level JSX element/fragment.
      let j = i, depth = 0;
      while (j < row.length) {
        if (row[j] === '<') depth += row[j + 1] === '/' ? -1 : 1;
        if (row[j] === '>') { if (depth === 0) { j++; break; } }
        j++;
      }
      // Fragment: <> ... </> — walk to the matching close.
      const close = row.indexOf('</>', i);
      const end = close === -1 ? j : close + 3;
      cells.push(row.slice(i, end)); i = end;
    } else {
      throw new Error(`unparsable KeyTable cell at: ${row.slice(i, i + 60)}`);
    }
  }
  return cells;
}

function parseRows(src) {
  const rows = [];
  let i = 0;
  while (i < src.length) {
    const start = src.indexOf('[', i);
    if (start === -1) break;
    let j = start + 1, depth = 1, inStr = null;
    while (j < src.length && depth > 0) {
      const c = src[j];
      if (inStr) { if (c === '\\') j++; else if (c === inStr) inStr = null; }
      else if (c === "'" || c === '"') inStr = c;
      else if (c === '[') depth++;
      else if (c === ']') depth--;
      j++;
    }
    const cells = scanCells(src.slice(start + 1, j - 1));
    if (cells.length !== 2) throw new Error(`KeyTable row with ${cells.length} cells: ${src.slice(start, j)}`);
    rows.push([inline(cells[0]), inline(cells[1])]);
    i = j;
  }
  if (rows.length === 0) throw new Error('KeyTable with no parsable rows');
  return rows;
}

function attr(tag, name) {
  const m = tag.match(new RegExp(`${name}=(?:"([^"]*)"|\\{([A-Za-z0-9_]+)\\})`));
  return m ? (m[1] !== undefined ? decode(m[1]) : `@${m[2]}`) : null;
}

function convertSection(body) {
  const out = [];
  let i = 0;
  const rest = () => body.slice(i);

  while (i < body.length) {
    const s = rest();
    let m;

    if ((m = s.match(/^\s*<section className="help-section">/))) { i += m[0].length; continue; }
    if ((m = s.match(/^\s*<\/section>\s*$/))) break;
    if ((m = s.match(/^\s+/)) && m[0].length === s.length) break;

    if ((m = s.match(/^\s*<(h2|h3|h4)>([\s\S]*?)<\/\1>/))) {
      const level = { h2: '##', h3: '###', h4: '####' }[m[1]];
      out.push(`${level} ${inline(m[2])}`);
      i += m[0].length; continue;
    }
    if ((m = s.match(/^\s*<p>([\s\S]*?)<\/p>/))) {
      out.push(inline(m[1])); i += m[0].length; continue;
    }
    if ((m = s.match(/^\s*<(ul|ol)>([\s\S]*?)<\/\1>/))) {
      const ordered = m[1] === 'ol';
      const items = [...m[2].matchAll(/<li>([\s\S]*?)<\/li>/g)].map((x) => inline(x[1]));
      if (items.length === 0) throw new Error('list with no items');
      out.push(items.map((it, n) => (ordered ? `${n + 1}. ${it}` : `- ${it}`)).join('\n'));
      i += m[0].length; continue;
    }
    if ((m = s.match(/^\s*<Tip title="([^"]*)">([\s\S]*?)<\/Tip>/))) {
      const title = decode(m[1]);
      out.push(`> **${title}**\n>\n> ${inline(m[2])}`);
      i += m[0].length; continue;
    }
    if ((m = s.match(/^\s*<KeyTable rows=\{\[([\s\S]*?)\]\}\s*\/>/))) {
      const rows = parseRows(m[1]);
      // Escape backslashes FIRST: doing pipes alone turns an input `\|` into
      // `\\|`, an escaped backslash followed by a live pipe, which splits the
      // cell. Order matters, not just coverage.
      const esc = (x) => x.replace(/\\/g, '\\\\').replace(/\|/g, '\\|');
      out.push([
        '| Key | Value |', '| --- | --- |',
        ...rows.map(([k, v]) => `| ${esc(k)} | ${esc(v)} |`),
      ].join('\n'));
      i += m[0].length; continue;
    }
    // <HelpFigure ...><Component /></HelpFigure>  or self-closing image form.
    // The attribute capture is [^>]* -- NOT [\s\S]*? -- so it cannot run past
    // its own closing bracket and pair with a later </HelpFigure>, swallowing
    // every heading and table in between.
    if ((m = s.match(/^\s*<HelpFigure([^>]*)>\s*<(\w+)\s*\/>\s*<\/HelpFigure>/))) {
      const caption = attr(m[1], 'caption');
      out.push(['```figure', `component: ${m[2]}`, `caption: ${caption}`, '```'].join('\n'));
      i += m[0].length; continue;
    }
    if ((m = s.match(/^\s*<HelpFigure((?:[^>]|>(?!\s*<))*?)\/>/))) {
      const fields = ['```figure', 'component: image'];
      for (const k of ['caption', 'alt', 'srcDark', 'srcLight']) {
        const v = attr(m[1], k);
        if (v) fields.push(`${k}: ${v}`);
      }
      fields.push('```');
      out.push(fields.join('\n'));
      i += m[0].length; continue;
    }
    // Preformatted sample output. Kept verbatim in a fenced block: it is
    // example console text, so a translator may localise it or leave it.
    if ((m = s.match(/^\s*<pre className="help-pre">\{`([\s\S]*?)`\}<\/pre>/))) {
      const body = m[1].replace(/^\n/, '').replace(/\s+$/, '');
      if (body.includes('```')) throw new Error('pre block contains a fence');
      out.push('```text\n' + body + '\n```');
      i += m[0].length; continue;
    }
    if ((m = s.match(/^\s*\{\/\*[\s\S]*?\*\/\}/))) { i += m[0].length; continue; }

    throw new Error(`unrecognised construct at:\n${s.slice(0, 160)}`);
  }
  return out.join('\n\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

const src = readFileSync(SRC, 'utf8');
mkdirSync(OUT_DIR, { recursive: true });
let n = 0;
for (const [name, slug] of Object.entries(SLUGS)) {
  const re = new RegExp(`export function ${name}\\(\\)\\s*\\{\\s*return \\(([\\s\\S]*?)\\n\\  \\);\\n\\}`);
  const m = src.match(re);
  if (!m) throw new Error(`section not found: ${name}`);
  writeFileSync(path.join(OUT_DIR, `${slug}.md`), convertSection(m[1]), 'utf8');
  n++;
}
console.log(`wrote ${n} markdown sections to ${path.relative(UI_ROOT, OUT_DIR)}`);
