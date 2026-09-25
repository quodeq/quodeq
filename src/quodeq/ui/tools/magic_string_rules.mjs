// Magic-string ratchet rules for the production UI: bare string literals the
// code branches on (`compared-literal`) or repeats (`repeated-literal`).
// Mirrors tools/check_magic_strings.py at the repo root; the fix is a named
// constant (module, feature constants module, src/constants.js) or a
// src/vocab/*.js member for a closed set. Counted by tools/check_magic_strings.mjs.
//
// Words the vocab gate owns (eslint.vocab.config.js) are skipped here so each
// literal has one gate. Both rules are syntactic: anything they over-report
// is fixed or named, never waived inline (the runner disables inline config).
import { VOCAB_WORDS } from '../eslint.vocab.config.js';

// A literal written this many times in one module needs a name.
const REPEAT_THRESHOLD = 3;

const isText = (node) => node?.type === 'Literal' && typeof node.value === 'string'
  && /[A-Za-z0-9]/.test(node.value) && !VOCAB_WORDS.has(node.value);

const EQUALITY = new Set(['===', '!==', '==', '!=']);

/** True when *node* sits under a JSX attribute, an import/export source, or
 * a top-level const initialiser, without crossing a function boundary. */
function inExemptScope(node) {
  let child = node;
  for (let p = node.parent; p; child = p, p = p.parent) {
    if (p.type === 'JSXAttribute') return true;
    if (p.type === 'ImportDeclaration' || p.type === 'ExportNamedDeclaration' && child === p.source
      || p.type === 'ExportAllDeclaration' || p.type === 'ImportExpression') return true;
    if (p.type === 'FunctionDeclaration' || p.type === 'FunctionExpression' || p.type === 'ArrowFunctionExpression') return false;
    if (p.type === 'VariableDeclarator' && child === p.init) {
      const decl = p.parent;
      const top = decl.parent?.type === 'Program' || decl.parent?.type === 'ExportNamedDeclaration';
      if (top && decl.kind === 'const') return true;
    }
  }
  return false;
}

/** True for a literal in a position that names itself: an object key or
 * value, a member-access key, a `t()` catalog key, a directive. */
function isKeyPosition(node) {
  const p = node.parent;
  if (!p) return false;
  if (p.type === 'Property') return true;
  if (p.type === 'MemberExpression' && p.property === node) return true;
  if (p.type === 'CallExpression' && p.callee.type === 'Identifier' && p.callee.name === 't' && p.arguments[0] === node) return true;
  if (p.type === 'ExpressionStatement' && p.directive) return true;
  return false;
}

const isTypeof = (node) => node?.type === 'UnaryExpression' && node.operator === 'typeof';

const comparedLiteral = {
  meta: { type: 'suggestion', schema: [], messages: { bare: "Bare string '{{value}}' in a comparison; name it (constant or src/vocab/*.js member)." } },
  create(context) {
    const report = (node) => context.report({ node, messageId: 'bare', data: { value: node.value } });
    return {
      BinaryExpression(node) {
        if (!EQUALITY.has(node.operator) || isTypeof(node.left) || isTypeof(node.right)) return;
        for (const side of [node.left, node.right]) if (isText(side)) report(side);
      },
      SwitchCase(node) {
        if (isText(node.test)) report(node.test);
      },
      CallExpression(node) {
        const callee = node.callee;
        if (callee.type !== 'MemberExpression' || callee.property.name !== 'includes' || callee.object.type !== 'ArrayExpression') return;
        for (const el of callee.object.elements) if (isText(el)) report(el);
      },
    };
  },
};

const repeatedLiteral = {
  meta: { type: 'suggestion', schema: [], messages: { repeated: "String '{{value}}' appears {{count}} times in this module; name it once." } },
  create(context) {
    const seen = new Map();
    return {
      Literal(node) {
        if (!isText(node) || isKeyPosition(node) || inExemptScope(node)) return;
        const list = seen.get(node.value) || [];
        list.push(node);
        seen.set(node.value, list);
      },
      'Program:exit'() {
        for (const [value, nodes] of seen) {
          if (nodes.length < REPEAT_THRESHOLD) continue;
          context.report({ node: nodes[0], messageId: 'repeated', data: { value, count: String(nodes.length) } });
        }
      },
    };
  },
};

export default { rules: { 'compared-literal': comparedLiteral, 'repeated-literal': repeatedLiteral } };
