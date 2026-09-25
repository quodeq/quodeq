/**
 * Pure merge of the local and shared project lists into one entry per
 * project. Matching: shared entry with the same id (your own publications),
 * else the same normalized git origin URL. Name-only collisions stay
 * separate on purpose (forks, same-named repos).
 */
import { PROJECT_SOURCE } from '../../vocab/projectSource.js';
import { PROJECT_ACTION } from './dashboardVocab.js';

const GIT_SUFFIX_LENGTH = 4; // ".git"

export function normalizeOriginUrl(url) {
  if (!url) return null;
  let u = String(url).trim();
  if (u.endsWith('/')) u = u.slice(0, -1);
  if (u.endsWith('.git')) u = u.slice(0, -GIT_SUFFIX_LENGTH);
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

/**
 * Name fields for an entry: the local side wins each one, the shared side
 * fills the gaps. Both sides are read through a `{}` stand-in so a missing
 * side reads as a missing field rather than a throw.
 */
function entryNames(local, shared) {
  const l = local || {};
  const s = shared || {};
  return {
    key: l.id || s.id || l.name || s.name,
    name: l.name || s.name,
    displayName: l.displayName || s.displayName || l.name || s.name,
  };
}

/** Which side(s) the entry was found on, for the row's chips. */
function entrySides(local, shared) {
  if (local && shared) return 'both';
  return local ? PROJECT_SOURCE.LOCAL : PROJECT_SOURCE.SHARED;
}

function makeEntry(local, shared) {
  return {
    ...entryNames(local, shared),
    local: local || null,
    shared: shared || null,
    chips: entrySides(local, shared),
    lastActivity: lastActivityOf(toMs(local?.latestDate), toMs(shared?.publishedAt)),
    score: local?.latestScore ?? shared?.latestScore ?? null,
  };
}

/** Shared entries indexed by id and by normalized origin URL. */
function indexShared(sharedProjects) {
  const byId = new Map();
  const byUrl = new Map();
  for (const s of sharedProjects) {
    if (s.id) byId.set(s.id, s);
    const u = normalizeOriginUrl(s.originUrl);
    if (u && !byUrl.has(u)) byUrl.set(u, s);
  }
  return { byId, byUrl };
}

/**
 * Pair each local project with at most one shared entry. Pass 1 claims by id;
 * pass 2 claims by normalized origin URL among whatever is still unclaimed,
 * so a local never double-dips a shared entry another local already matched.
 */
function claimShared(localProjects, { byId, byUrl }) {
  const claimed = new Set();
  const matchByLocal = new Map();
  const claim = (l, s) => {
    if (!s || claimed.has(s)) return;
    claimed.add(s);
    matchByLocal.set(l, s);
  };

  for (const l of localProjects) {
    if (l.id) claim(l, byId.get(l.id));
  }
  for (const l of localProjects) {
    if (matchByLocal.has(l)) continue;
    const u = normalizeOriginUrl(l.originUrl);
    if (u) claim(l, byUrl.get(u));
  }
  return { claimed, matchByLocal };
}

export function mergeProjects(localProjects = [], sharedProjects = []) {
  const { claimed, matchByLocal } = claimShared(localProjects, indexShared(sharedProjects));
  const merged = localProjects.map((l) => makeEntry(l, matchByLocal.get(l) || null));
  for (const s of sharedProjects) {
    if (!claimed.has(s)) merged.push(makeEntry(null, s));
  }
  return merged;
}

/**
 * Compare the two sides by done-run identity: exact, and immune to the
 * date-only-vs-epoch skew a same-day timestamp comparison cannot resolve.
 *
 * local.latestRunId is the newest run of ANY status, but publish only ever
 * copies done runs into the shared repo, so comparing raw latestRunId would
 * show a permanent false 'update' once a later local run fails or is
 * cancelled: it could never again equal shared's id. latestDoneRunId is the
 * newest run that actually finished, so use that instead, falling back to
 * latestRunId on the shared side (every shared entry's runs are done runs
 * already, by construction of publish).
 *
 * Returns undefined when the shared side has no run id to compare against, so
 * the caller falls back to timestamps.
 *
 * @returns {'update'|null|undefined}
 */
function compareDoneRuns(local, shared) {
  const localId = local?.latestDoneRunId ?? null;
  const sharedId = shared?.latestDoneRunId ?? shared?.latestRunId ?? null;
  if (sharedId == null) return undefined;
  // No done local run to publish -- nothing new to offer, already in sync.
  if (localId == null) return null;
  return localId !== sharedId ? PROJECT_ACTION.UPDATE : null;
}

/** Action for an entry present on both sides. */
function bothSidesAction(local, shared) {
  const byRunId = compareDoneRuns(local, shared);
  if (byRunId !== undefined) return byRunId;
  // Absent latestRunId means no manifest-bearing run was ever produced for
  // that side (list_runs only counts runs with an evidence manifest), not
  // strictly "zero runs" -- a run can exist on disk and still not count.
  const lastEval = toMs(local?.latestDate);
  const publishedAt = toMs(shared?.publishedAt);
  if (lastEval != null && (publishedAt == null || lastEval > publishedAt)) return PROJECT_ACTION.UPDATE;
  return null;
}

export function deriveAction(entry, { configured }) {
  const { local, shared } = entry;
  if (local && !shared) return configured ? PROJECT_ACTION.PUBLISH : null;
  if (!local && shared) return PROJECT_ACTION.PULL;
  return bothSidesAction(local, shared);
}
