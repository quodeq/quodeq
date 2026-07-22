/**
 * Pure merge of the local and shared project lists into one entry per
 * project. Matching: shared entry with the same id (your own publications),
 * else the same normalized git origin URL. Name-only collisions stay
 * separate on purpose (forks, same-named repos).
 */

export function normalizeOriginUrl(url) {
  if (!url) return null;
  let u = String(url).trim();
  if (u.endsWith('/')) u = u.slice(0, -1);
  if (u.endsWith('.git')) u = u.slice(0, -4);
  return u || null;
}

function toMs(value) {
  if (value == null) return null;
  if (typeof value === 'number') return value;
  const t = Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

function lastActivityOf(lastEval, publishedAt) {
  if (lastEval == null && publishedAt == null) return null;
  if (lastEval == null) return publishedAt;
  if (publishedAt == null) return lastEval;
  return Math.max(lastEval, publishedAt);
}

function makeEntry(local, shared) {
  const lastEval = toMs(local?.latestDate);
  const publishedAt = toMs(shared?.publishedAt);
  return {
    key: local?.id || shared?.id || local?.name || shared?.name,
    name: local?.name || shared?.name,
    displayName: local?.displayName || shared?.displayName || local?.name || shared?.name,
    local: local || null,
    shared: shared || null,
    chips: local && shared ? 'both' : local ? 'local' : 'shared',
    lastActivity: lastActivityOf(lastEval, publishedAt),
    score: local?.latestScore ?? shared?.latestScore ?? null,
  };
}

export function mergeProjects(localProjects = [], sharedProjects = []) {
  const sharedById = new Map();
  const sharedByUrl = new Map();
  for (const s of sharedProjects) {
    if (s.id) sharedById.set(s.id, s);
    const u = normalizeOriginUrl(s.originUrl);
    if (u && !sharedByUrl.has(u)) sharedByUrl.set(u, s);
  }

  // Each shared entry may be claimed by at most one local project. Pass 1
  // claims by id; pass 2 claims by normalized origin URL among whatever is
  // still unclaimed, so a local never double-dips a shared entry that
  // another local already matched.
  const claimed = new Set();
  const matchByLocal = new Map();

  for (const l of localProjects) {
    if (!l.id) continue;
    const s = sharedById.get(l.id);
    if (s && !claimed.has(s)) {
      claimed.add(s);
      matchByLocal.set(l, s);
    }
  }

  for (const l of localProjects) {
    if (matchByLocal.has(l)) continue;
    const u = normalizeOriginUrl(l.originUrl);
    if (!u) continue;
    const s = sharedByUrl.get(u);
    if (s && !claimed.has(s)) {
      claimed.add(s);
      matchByLocal.set(l, s);
    }
  }

  const merged = localProjects.map((l) => makeEntry(l, matchByLocal.get(l) || null));
  for (const s of sharedProjects) {
    if (!claimed.has(s)) merged.push(makeEntry(null, s));
  }
  return merged;
}

export function deriveAction(entry, { configured }) {
  const { local, shared } = entry;
  if (local && !shared) return configured ? 'publish' : null;
  if (!local && shared) return 'pull';
  // Both sides present. Prefer run identity: it's exact and immune to the
  // date-only-vs-epoch skew a same-day timestamp comparison can't resolve.
  // Legacy shared entries omit latestRunId (a project with zero runs), so
  // fall back to the old timestamp comparison whenever either id is absent.
  if (local?.latestRunId && shared?.latestRunId) {
    return local.latestRunId !== shared.latestRunId ? 'update' : null;
  }
  const lastEval = toMs(local?.latestDate);
  const publishedAt = toMs(shared?.publishedAt);
  if (lastEval != null && (publishedAt == null || lastEval > publishedAt)) return 'update';
  return null;
}
