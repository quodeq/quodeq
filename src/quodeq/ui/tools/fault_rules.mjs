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

// Log methods that count as surfacing the error, on `console` or on any
// project logger wrapper.
const LOG_METHODS = new Set(['warn', 'error', 'debug']);

/** Nodes whose bodies belong to some other catch, or run later. */
const WALK_STOPS = new Set([
  'CatchClause',
  'FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression',
]);

/**
 * What the catch body does with the error: whether it mentions any of the
 * bound names, throws, or logs. A plain recursive walk is enough -- the
 * bodies in question are a handful of statements, and scope analysis would
 * not change the answer for any shape seen here.
 *
 * The walk stops at a nested catch (its handling covers its own error, not
 * this one) and at a nested function body (it runs later, if at all).
 */
function inspectCatchBody(body, names) {
  const seen = { usesParam: false, throws: false, logs: false };
  const walk = (node) => {
    if (!node || typeof node.type !== 'string') return;
    if (WALK_STOPS.has(node.type)) return;
    if (node.type === 'Identifier' && names.has(node.name)) seen.usesParam = true;
    if (node.type === 'ThrowStatement') seen.throws = true;
    if (node.type === 'CallExpression' && node.callee?.type === 'MemberExpression') {
      if (node.callee.object?.name === 'console') seen.logs = true;
      if (LOG_METHODS.has(node.callee.property?.name)) seen.logs = true;
    }
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

/** The variable `name` binds to at `scope`, walking outward. */
function resolveVariable(scope, name) {
  for (let s = scope; s; s = s.upper) {
    const found = s.variables.find((v) => v.name === name);
    if (found) return found;
  }
  return null;
}

/**
 * True when every binding of this variable is an async function -- a
 * declaration or a `const f = async () => {}`. A parameter, an import or a
 * plain value resolves here and answers false, which is the whole point:
 * sharing a name with an async function is not being one.
 */
function bindsAsyncFunction(variable) {
  if (!variable || variable.defs.length === 0) return false;
  return variable.defs.some((def) => {
    if (def.type === 'FunctionName') return isAsyncFn(def.node);
    if (def.type === 'Variable') return isAsyncFn(def.node.init);
    return false;
  });
}

const floatingPromise = {
  meta: {
    type: 'problem',
    docs: { description: 'the result of an async call must be awaited, returned, caught or voided' },
    schema: [],
  },
  create(context) {
    return {
      ExpressionStatement(node) {
        const expr = node.expression;
        if (expr?.type !== 'CallExpression') return;
        const prop = calleeProperty(expr.callee);
        // Only the OUTERMOST `.catch(...)` exempts the statement. `p.catch(x)`
        // is handled; `p.catch(x).then(y)` is not, because `then` can reject
        // in turn and nothing is left to catch it.
        if (prop === 'catch') return;
        // A call to a function this file declares `async`, resolved through
        // scope so a prop or parameter that shadows the name is not mistaken
        // for it. Cross-module calls stay invisible without types: a missed
        // one is a false negative, never a false positive.
        const floats = prop === 'then'
          || (expr.callee?.type === 'Identifier' && bindsAsyncFunction(
            resolveVariable(context.sourceCode.getScope(node), expr.callee.name),
          ));
        if (!floats) return;
        context.report({
          node: expr,
          message: 'promise result is discarded -- await it, return it, add .catch(), or void it deliberately',
        });
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

// `get` is the ambiguous one: Map#get can miss, but so are named an HTTP
// client (`api.get(url)`), URLSearchParams and Headers, which do not have
// the same miss semantics. Require the receiver to read as a collection.
const MAPPISH_RECEIVER = /map|cache|registry|index|by[A-Z]/i;

// Promise plumbing on a lookup result is not a dereference that can hit null.
const PROMISE_METHODS = new Set(['then', 'catch', 'finally']);

/** Identifier-ish name of a call's receiver: `a.get` -> a, `x.by.get` -> by. */
function receiverName(callee) {
  const object = callee.object;
  if (object?.type === 'Identifier') return object.name;
  if (object?.type === 'MemberExpression') return object.property?.name ?? null;
  return null;
}

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
        if (!node.computed && PROMISE_METHODS.has(node.property?.name)) return;
        const call = node.object;
        if (call?.type !== 'CallExpression') return;
        if (call.callee?.type !== 'MemberExpression') return;
        const lookup = call.callee.property?.name;
        if (!NULLABLE_LOOKUPS.has(lookup)) return;
        if (lookup === 'get' && !MAPPISH_RECEIVER.test(receiverName(call.callee) ?? '')) return;
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
