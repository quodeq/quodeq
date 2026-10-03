// Custom ESLint rule behind the naming ratchet (eslint.naming.config.js).
// Locks the UI's existing naming style, which the inventory found clean:
//   - a module-level `const` bound to a string/number/boolean literal or to
//     Object.freeze({...}) / Object.freeze([...]) is UPPER_SNAKE_CASE;
//   - a module-level function declaration is camelCase, or PascalCase in a
//     .jsx file (a component).
// One leading underscore is allowed on both (the "module-private" prefix the
// tree already uses). Arrow functions bound to a const are not checked: some
// are deliberately named like constants (SSE_ENABLED, NEVER_QUERIED).
const UPPER_SNAKE = /^_?[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$/;
const CAMEL = /^_?[a-z][a-zA-Z0-9]*$/;
const PASCAL = /^[A-Z][a-zA-Z0-9]*$/;
const SCALAR_TYPES = new Set(['string', 'number', 'boolean']);

function isScalarLiteral(node) {
  if (node.type === 'UnaryExpression' && node.operator === '-') return isScalarLiteral(node.argument);
  return node.type === 'Literal' && SCALAR_TYPES.has(typeof node.value);
}

function isFrozenLiteral(node) {
  const { callee } = node;
  return node.type === 'CallExpression'
    && callee.type === 'MemberExpression'
    && callee.object.name === 'Object' && callee.property.name === 'freeze'
    && ['ObjectExpression', 'ArrayExpression'].includes(node.arguments[0]?.type);
}

function isModuleLevel(node) {
  const { parent } = node;
  if (parent.type === 'Program') return true;
  return ['ExportNamedDeclaration', 'ExportDefaultDeclaration'].includes(parent.type)
    && parent.parent.type === 'Program';
}

export default {
  meta: {
    type: 'suggestion',
    schema: [],
    messages: {
      constant: "Module constant '{{name}}' holds a literal or frozen object; name it UPPER_SNAKE_CASE.",
      function: "Module function '{{name}}' must be camelCase{{extra}}.",
    },
  },
  create(context) {
    const isJsx = context.filename.endsWith('.jsx');
    return {
      VariableDeclaration(node) {
        if (node.kind !== 'const' || !isModuleLevel(node)) return;
        for (const { id, init } of node.declarations) {
          if (id.type !== 'Identifier' || !init) continue;
          if (!isScalarLiteral(init) && !isFrozenLiteral(init)) continue;
          if (!UPPER_SNAKE.test(id.name)) context.report({ node: id, messageId: 'constant', data: { name: id.name } });
        }
      },
      FunctionDeclaration(node) {
        if (!node.id || !isModuleLevel(node)) return;
        const { name } = node.id;
        if (CAMEL.test(name) || (isJsx && PASCAL.test(name))) return;
        const extra = isJsx ? ' (or PascalCase for a component)' : '';
        context.report({ node: node.id, messageId: 'function', data: { name, extra } });
      },
    };
  },
};
