// Custom ratchet rules for the four JS fault-tolerance failure modes the
// stock rule sets do not cover here (R-FT-1..3).
//
// All four are syntactic heuristics. None of them can prove a promise floats
// or a lookup misses -- that needs types the codebase does not carry. They
// are tuned to catch the shapes the audit actually found, and anything they
// over-report is grandfathered per-file in tools/fault_baseline.json, same
// contract as the other gates. Counted by tools/check_fault.mjs.

// --- swallowed-catch ---------------------------------------------------

/** Identifier names bound by a catch parameter, including destructuring. */
function boundNames(param) {
  const names = new Set();
  if (!param) return names;
  const walk = (node) => {
    if (!node || typeof node.type !== 'string') return;
    if (node.type === 'Identifier') { names.add(node.name); return; }
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(walk);
      else if (value && typeof value.type === 'string') walk(value);
    }
  };
  walk(param);
  return names;
}

/**
 * What the catch body does with the error: whether it mentions any of the
 * bound names, throws, or logs. A plain recursive walk is enough -- the
 * bodies in question are a handful of statements, and scope analysis would
 * not change the answer for any shape seen here.
 */
function inspectCatchBody(body, names) {
  const seen = { usesParam: false, throws: false, logs: false };
  const walk = (node) => {
    if (!node || typeof node.type !== 'string') return;
    if (node.type === 'Identifier' && names.has(node.name)) seen.usesParam = true;
    if (node.type === 'ThrowStatement') seen.throws = true;
    if (node.type === 'CallExpression'
      && node.callee?.type === 'MemberExpression'
      && node.callee.object?.name === 'console') seen.logs = true;
    for (const [key, value] of Object.entries(node)) {
      if (key === 'parent') continue;
      if (Array.isArray(value)) value.forEach(walk);
      else if (value && typeof value.type === 'string') walk(value);
    }
  };
  body.forEach(walk);
  return seen;
}

const swallowedCatch = {
  meta: {
    type: 'problem',
    docs: { description: 'a catch block must log, surface or rethrow the error' },
    schema: [],
  },
  create(context) {
    return {
      CatchClause(node) {
        const body = node.body?.body ?? [];
        const names = boundNames(node.param);
        if (body.length > 0) {
          const { usesParam, throws, logs } = inspectCatchBody(body, names);
          if (usesParam || throws || logs) return;
        }
        context.report({
          node,
          message: 'catch swallows the error -- log it (console.warn with a [module] prefix), surface it, or rethrow',
        });
      },
    };
  },
};

// --- floating-promise --------------------------------------------------

/** True for a function-ish node declared `async`. */
function isAsyncFn(node) {
  return Boolean(node)
    && (node.type === 'FunctionExpression' || node.type === 'ArrowFunctionExpression'
      || node.type === 'FunctionDeclaration')
    && node.async === true;
}

/** The outermost `.name` of a call chain, e.g. `a().b().catch()` -> catch. */
function calleeProperty(callee) {
  return callee?.type === 'MemberExpression' ? callee.property?.name : undefined;
}

const floatingPromise = {
  meta: {
    type: 'problem',
    docs: { description: 'the result of an async call must be awaited, returned, caught or voided' },
    schema: [],
  },
  create(context) {
    // Names of async functions declared in this file. Cross-module calls are
    // invisible without types, so this is deliberately file-local: a missed
    // one is a false negative, never a false positive.
    const asyncNames = new Set();
    const remember = (name, fn) => { if (name && isAsyncFn(fn)) asyncNames.add(name); };

    return {
      FunctionDeclaration(node) { remember(node.id?.name, node); },
      VariableDeclarator(node) { remember(node.id?.name, node.init); },
      Property(node) { remember(node.key?.name, node.value); },
      MethodDefinition(node) { remember(node.key?.name, node.value); },

      // Run after the whole file is walked so a call above its declaration
      // still resolves.
      'Program:exit'(program) {
        const check = (node) => {
          if (!node || typeof node.type !== 'string') return;
          if (node.type === 'ExpressionStatement') {
            const expr = node.expression;
            if (expr?.type === 'CallExpression') {
              const prop = calleeProperty(expr.callee);
              // `.catch(...)` at the end of the chain handles the rejection.
              if (prop !== 'catch') {
                const floats = prop === 'then'
                  || (expr.callee?.type === 'Identifier' && asyncNames.has(expr.callee.name));
                if (floats) {
                  context.report({
                    node: expr,
                    message: 'promise result is discarded -- await it, return it, add .catch(), or void it deliberately',
                  });
                }
              }
            }
          }
          for (const [key, value] of Object.entries(node)) {
            if (key === 'parent') continue;
            if (Array.isArray(value)) value.forEach(check);
            else if (value && typeof value.type === 'string') check(value);
          }
        };
        check(program);
      },
    };
  },
};

// --- raw-storage-access ------------------------------------------------

const STORAGE_OBJECTS = new Set(['localStorage', 'sessionStorage']);

const rawStorageAccess = {
  meta: {
    type: 'problem',
    docs: { description: 'web storage must go through the adapter that handles private mode and quota' },
    schema: [],
  },
  create(context) {
    return {
      MemberExpression(node) {
        const direct = node.object?.type === 'Identifier' && STORAGE_OBJECTS.has(node.object.name);
        // `window.localStorage.getItem(...)`: the storage object is itself a
        // member expression, so match on its property instead.
        const viaWindow = node.object?.type === 'MemberExpression'
          && STORAGE_OBJECTS.has(node.object.property?.name);
        if (!direct && !viaWindow) return;
        context.report({
          node,
          message: 'raw web storage access -- use src/adapters/storage.js (readString/writeString/readJSON/writeJSON/removeKey)',
        });
      },
    };
  },
};

// --- unguarded-lookup-deref --------------------------------------------

// Lookups whose miss case is a null or undefined rather than a throw. Each
// one is a documented "returns null/undefined when not found" API.
const NULLABLE_LOOKUPS = new Set(['find', 'querySelector', 'match', 'get', 'getElementById']);

const unguardedLookupDeref = {
  meta: {
    type: 'problem',
    docs: { description: 'a nullable lookup result must be guarded before it is dereferenced' },
    schema: [],
  },
  create(context) {
    return {
      MemberExpression(node) {
        if (node.optional) return; // `?.` already handles the miss.
        const call = node.object;
        if (call?.type !== 'CallExpression') return;
        if (call.callee?.type !== 'MemberExpression') return;
        if (!NULLABLE_LOOKUPS.has(call.callee.property?.name)) return;
        context.report({
          node,
          message: 'lookup can return null/undefined -- use ?. or guard the result before dereferencing it',
        });
      },
    };
  },
};

export default {
  rules: {
    'swallowed-catch': swallowedCatch,
    'floating-promise': floatingPromise,
    'raw-storage-access': rawStorageAccess,
    'unguarded-lookup-deref': unguardedLookupDeref,
  },
};
