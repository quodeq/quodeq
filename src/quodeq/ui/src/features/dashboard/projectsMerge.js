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
    lastActivity: Math.max(lastEval ?? 0, publishedAt ?? 0) || null,
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
  const claimed = new Set();
  const merged = [];
  for (const l of localProjects) {
    const match =
      (l.id && sharedById.get(l.id)) ||
      sharedByUrl.get(normalizeOriginUrl(l.originUrl)) ||
      null;
    if (match) claimed.add(match);
    merged.push(makeEntry(l, match));
  }
  for (const s of sharedProjects) {
    if (!claimed.has(s)) merged.push(makeEntry(null, s));
  }
  return merged;
}

export function deriveAction(entry, { configured }) {
  const { local, shared } = entry;
  if (local && !shared) return configured ? 'publish' : null;
  if (!local && shared) return 'pull';
  const lastEval = toMs(local?.latestDate);
  const publishedAt = toMs(shared?.publishedAt);
  if (lastEval != null && (publishedAt == null || lastEval > publishedAt)) return 'update';
  return null;
}
