// Custom ratchet rules for the two string surfaces react/jsx-no-literals
// cannot see.
//
// 1. Visible attributes. jsx-no-literals has a noAttributeStrings option, but
//    it is inert while ignoreProps is on, and turning both on flags ~6.7k
//    className/role/svg-path strings because the rule cannot tell a visible
//    attribute from a structural one. So: check a fixed allowlist of
//    attributes that render as text.
//
// 2. Prose in .js. The ratchet globs *.jsx and jsx-no-literals only sees JSX
//    literals, so a toast string assigned to a variable in a hook is
//    invisible to it by construction -- which is exactly where the error and
//    confirmation copy lives.
//
// Both are counted by tools/check_strings.mjs against the shared per-file
// baseline in tools/strings_baseline.json.

// Attributes whose value is read out or displayed to a person.
const VISIBLE_ATTRS = new Set(['title', 'placeholder', 'aria-label', 'alt']);

// Placeholder values that are examples of what to TYPE, not text to read:
// a translator handed these would corrupt them. Same identity-vs-display
// call made throughout the sweep for enum keys and taxonomy codes.
const IDENTITY_VALUES = new Set([
  'git@github.com:org/repo.git',
  'https://github.com/team/results.git',
  'http://localhost:8000',
  'mlx-community/gemma-3-4b-it-4bit',
  '/new/path/to/repo',
  '1234',
]);

const noLiteralVisibleAttrs = {
  meta: {
    type: 'problem',
    docs: { description: 'visible JSX attributes must come from the string catalog' },
    schema: [],
  },
  create(context) {
    return {
      JSXAttribute(node) {
        const name = node.name?.type === 'JSXNamespacedName'
          ? `${node.name.namespace.name}:${node.name.name.name}`
          : node.name?.name;
        if (!VISIBLE_ATTRS.has(name)) return;
        const value = node.value;
        if (!value || value.type !== 'Literal' || typeof value.value !== 'string') return;
        if (IDENTITY_VALUES.has(value.value)) return;
        context.report({
          node: value,
          message: `hardcoded ${name}="${value.value}" -- move it to en.json and render via t()`,
        });
      },
    };
  },
};

// Shapes that are code, not copy. Checked before the prose test so the rule
// stays quiet about stylesheets and media queries.
const NOT_PROSE = [
  /^\(/,                                   // media query: (prefers-color-scheme: dark)
  /^[.#>]/,                                // CSS selector
  /^\[[A-Za-z][\w.]*\]/,                   // log prefix: [useProviderSettings] ...
  /\d+px|sans-serif|monospace|-apple-system/, // font shorthand
  /var\(--|^color-mix\(/,                  // CSS custom properties / color functions
  // Class list. Tokens may END in a separator: `qd-confirm-btn--` is a BEM
  // modifier prefix waiting for the interpolated half of a template.
  /^https?:\/\//,
  /[<>]|style=|class(Name)?=/,             // hand-built markup fragments
  /^(rotate|translate|scale|matrix)\(/,    // SVG/CSS transform pieces
  /\b\d*\.?\d+m?s\b/,                      // CSS duration: "transform 0.5s ease"
];

// A class list may mix hyphenated and plain tokens ("badge badge--danger",
// "chip small"). Require every token to look like an identifier AND at least
// one to carry a separator, so ordinary two-word copy ("months ago", "grade
// formula") is not swallowed.
function isClassList(text) {
  const tokens = text.split(/\s+/);
  if (!tokens.every((tok) => /^[a-z0-9][a-z0-9_-]*$/.test(tok))) return false;
  return tokens.some((tok) => /[-_]/.test(tok));
}

// Attributes and style-object keys whose value is structural no matter what
// it looks like. Shape filters alone cannot cover these: "panel settings-
// section" and "chip small" are class lists that read as two English words,
// and "Server log" is real copy that reads like neither. Position in the
// tree is the reliable signal; the shape filters stay as a backstop for
// plain-.js code that has no JSX around it.
const STRUCTURAL_ATTRS = new Set([
  'className', 'class', 'style', 'rel', 'target', 'href', 'src', 'id', 'key',
  'name', 'type', 'role', 'htmlFor', 'xmlns', 'viewBox', 'preserveAspectRatio',
  'd', 'points', 'transform', 'clipPath', 'fill', 'stroke', 'strokeDasharray',
  'strokeLinecap', 'strokeLinejoin', 'fontFamily', 'textAnchor', 'dominantBaseline',
  'dataTestId', 'data-testid', 'autoComplete', 'inputMode', 'encType', 'method',
]);

const STRUCTURAL_STYLE_KEYS = new Set([
  'transition', 'transform', 'font', 'fontFamily', 'clipPath', 'clip', 'animation',
  'background', 'backgroundImage', 'filter', 'willChange', 'gridTemplateColumns',
  'gridTemplateAreas', 'gridArea', 'boxShadow', 'cursor', 'content',
]);

/** Name of the enclosing JSX attribute, climbing through value wrappers. */
function enclosingAttribute(node) {
  let cur = node;
  for (let depth = 0; cur && depth < 6; depth++) {
    const parent = cur.parent;
    if (!parent) return null;
    if (parent.type === 'JSXAttribute') {
      return parent.name?.type === 'JSXNamespacedName'
        ? `${parent.name.namespace.name}:${parent.name.name.name}`
        : parent.name?.name ?? null;
    }
    // Only climb through things that shape a value, so a string nested in an
    // unrelated call does not inherit an attribute's exemption.
    if (!['JSXExpressionContainer', 'TemplateLiteral', 'ConditionalExpression',
      'LogicalExpression', 'BinaryExpression'].includes(parent.type)) return null;
    cur = parent;
  }
  return null;
}

/** True when the literal is a value in a style-ish object under a CSS key. */
function inStructuralStyleValue(node) {
  let cur = node;
  for (let depth = 0; cur && depth < 4; depth++) {
    const parent = cur.parent;
    if (!parent) return false;
    if (parent.type === 'Property' && parent.value === cur) {
      const key = parent.key?.name ?? parent.key?.value;
      return typeof key === 'string' && STRUCTURAL_STYLE_KEYS.has(key);
    }
    if (!['TemplateLiteral', 'ConditionalExpression', 'LogicalExpression',
      'BinaryExpression'].includes(parent.type)) return false;
    cur = parent;
  }
  return false;
}

// Arguments to string matching are patterns, not copy: line.startsWith('diff
// --git') is parsing, and translating it would break the parse.
const MATCHER_METHODS = new Set([
  'startsWith', 'endsWith', 'includes', 'indexOf', 'lastIndexOf',
  'split', 'match', 'test', 'search', 'localeCompare',
]);

function isMatcherArgument(node) {
  const parent = node.parent;
  if (parent?.type !== 'CallExpression' || !parent.arguments.includes(node)) return false;
  const callee = parent.callee;
  return callee?.type === 'MemberExpression'
    && MATCHER_METHODS.has(callee.property?.name);
}

function inStructuralPosition(node) {
  if (isMatcherArgument(node)) return true;
  const attr = enclosingAttribute(node);
  if (attr && STRUCTURAL_ATTRS.has(attr)) return true;
  return inStructuralStyleValue(node);
}

// Sentence-shaped: at least two words, one real lowercase word, long enough
// that it is copy rather than a token. Deliberately loose -- anything it
// over-reports that is genuinely developer-facing gets grandfathered in the
// baseline, same contract as the JSX ratchet.
function isProse(s) {
  const text = s.trim();
  if (text.length < 10) return false;
  if (text.split(/\s+/).length < 2) return false;
  if (!/[a-z]{3}/.test(text)) return false;
  if (isClassList(text)) return false;
  return !NOT_PROSE.some((re) => re.test(text));
}

/** Developer-facing sinks: console.*, thrown Errors, and Error construction. */
function inDevChannel(node) {
  let cur = node;
  for (let depth = 0; cur && depth < 4; depth++) {
    const parent = cur.parent;
    if (!parent) return false;
    if (parent.type === 'CallExpression' || parent.type === 'NewExpression') {
      const callee = parent.callee;
      if (callee?.type === 'MemberExpression' && callee.object?.name === 'console') return true;
      if (callee?.type === 'Identifier' && /^(Error|TypeError|RangeError)$/.test(callee.name)) return true;
    }
    if (parent.type === 'ThrowStatement') return true;
    // Only climb through value-shaping wrappers, so a string buried in an
    // unrelated expression does not inherit a console call's exemption.
    if (!['BinaryExpression', 'TemplateLiteral', 'ConditionalExpression', 'LogicalExpression'].includes(parent.type)
      && depth > 0) return false;
    cur = parent;
  }
  return false;
}

const noProseLiterals = {
  meta: {
    type: 'problem',
    docs: { description: 'user-visible prose in .js must come from the string catalog' },
    schema: [],
  },
  create(context) {
    return {
      Literal(node) {
        if (typeof node.value !== 'string') return;
        if (node.parent?.type === 'ImportDeclaration') return;
        if (node.parent?.type === 'ExportNamedDeclaration') return;
        if (node.parent?.type === 'Property' && node.parent.key === node) return;
        if (!isProse(node.value)) return;
        if (inDevChannel(node)) return;
        if (inStructuralPosition(node)) return;
        context.report({
          node,
          message: `hardcoded user-visible string "${node.value.slice(0, 60)}" -- move it to en.json and render via t()`,
        });
      },
      // Prose split across `a ${x} b` is invisible to the Literal handler,
      // and it is where the interpolated sentences live. Report the quasi,
      // not the whole template, so the message names the offending text.
      TemplateLiteral(node) {
        if (inDevChannel(node)) return;
        if (inStructuralPosition(node)) return;
        for (const quasi of node.quasis) {
          const text = quasi.value.cooked ?? '';
          if (!isProse(text)) continue;
          context.report({
            node: quasi,
            message: `hardcoded user-visible text "${text.trim().slice(0, 60)}" in a template literal -- use a whole-sentence catalog key with {placeholders}`,
          });
        }
      },
    };
  },
};

export default {
  rules: {
    'no-literal-visible-attrs': noLiteralVisibleAttrs,
    'no-prose-literals': noProseLiterals,
  },
};
