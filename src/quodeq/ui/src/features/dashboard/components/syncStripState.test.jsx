// A vitest file (not node:test): syncStripState imports the api module, which reads import.meta.env.
import { describe, it, expect } from 'vitest';
import { STRIP_STATE, pickStripState, progressLabel, barPercent } from './syncStripState.js';
import { SYNC_KIND, SYNC_PHASE } from '../../../vocab/syncPhase.js';

const idle = { phase: null };
const running = (phase) => ({ phase });
const failed = (finishedAt) => ({ phase: SYNC_PHASE.ERROR, finishedAt });
const done = (finishedAt) => ({ phase: SYNC_PHASE.DONE, finishedAt });
const status = (over = {}) => ({ configured: true, connect: idle, refresh: idle, ...over });

// [name, input, expected kind]
const CASES = [
  ['nothing configured, nothing running: hidden', { status: status({ configured: false }) }, STRIP_STATE.HIDDEN],
  ['no status yet: hidden', { status: undefined }, STRIP_STATE.HIDDEN],
  ['a first connect shows before configured', { status: status({ configured: false, connect: running(SYNC_PHASE.DOWNLOADING) }) }, STRIP_STATE.PROGRESS],
  ['connect active outranks a refresh error', { status: status({ connect: running(SYNC_PHASE.READING), refresh: failed(1) }) }, STRIP_STATE.PROGRESS],
  ['connect active outranks offline', { status: status({ connect: running(SYNC_PHASE.CONNECTING) }), offline: true }, STRIP_STATE.PROGRESS],
  ['refresh active', { status: status({ refresh: running(SYNC_PHASE.CONNECTING) }) }, STRIP_STATE.PROGRESS],
  ['offline outranks updateFailed', { status: status({ refresh: failed(1) }), offline: true, updateFailed: true }, STRIP_STATE.OFFLINE],
  ['updateFailed outranks loadFailed', { status: status(), updateFailed: true, loadFailed: true }, STRIP_STATE.UPDATE_FAILED],
  ['a refresh ERROR is an update failure', { status: status({ refresh: failed(5) }) }, STRIP_STATE.UPDATE_FAILED],
  ['loadFailed alone', { status: status(), loadFailed: true }, STRIP_STATE.LOAD_FAILED],
  ['loadFailed outranks a connect error (which is card-only)', { status: status({ connect: failed(5) }), loadFailed: true }, STRIP_STATE.LOAD_FAILED],
  ['a refresh ERROR older than a later connect DONE no longer counts', { status: status({ refresh: failed(5), connect: done(9) }) }, STRIP_STATE.SYNCED],
  ['a refresh ERROR newer than the last connect DONE still counts', { status: status({ refresh: failed(9), connect: done(5) }) }, STRIP_STATE.UPDATE_FAILED],
  ['configured + connect ERROR (a failed change of repository): synced for the working repository', { status: status({ connect: failed(5) }) }, STRIP_STATE.SYNCED],
  ['unconfigured + connect ERROR (a failed first connect): hidden, the card shows the error', { status: status({ configured: false, connect: failed(5) }) }, STRIP_STATE.HIDDEN],
  ['configured, nothing to report: synced', { status: status() }, STRIP_STATE.SYNCED],
];

describe('pickStripState', () => {
  it.each(CASES)('%s', (_name, input, expected) => {
    expect(pickStripState(input).kind).toBe(expected);
  });

  it('hands the running slot and its kind to the progress row', () => {
    const refresh = running(SYNC_PHASE.DOWNLOADING);
    expect(pickStripState({ status: status({ refresh }) })).toEqual({ kind: STRIP_STATE.PROGRESS, slot: refresh, slotKind: SYNC_KIND.REFRESH });
  });

  it("git's resolving and checkout phases are still progress", () => {
    expect(pickStripState({ status: status({ connect: running(SYNC_PHASE.RESOLVING) }) }).kind).toBe(STRIP_STATE.PROGRESS);
    expect(pickStripState({ status: status({ refresh: running(SYNC_PHASE.CHECKOUT) }) }).kind).toBe(STRIP_STATE.PROGRESS);
  });
});

describe('progressLabel and barPercent', () => {
  const url = 'https://github.com/team/evaluations.git';

  it('names each phase of a connect, with a percent where git reports one', () => {
    expect(progressLabel({ phase: SYNC_PHASE.CONNECTING }, SYNC_KIND.CONNECT, url)).toBe('connecting to github.com/team/evaluations…');
    expect(progressLabel({ phase: SYNC_PHASE.DOWNLOADING, percent: 38, bytes: 43_201_536 }, SYNC_KIND.CONNECT, url)).toBe('downloading evaluations · 38% · 41.2 MB');
    expect(progressLabel({ phase: SYNC_PHASE.RESOLVING, percent: 60 }, SYNC_KIND.CONNECT, url)).toBe('resolving · 60%');
    expect(progressLabel({ phase: SYNC_PHASE.CHECKOUT, percent: 7 }, SYNC_KIND.CONNECT, url)).toBe('checking out · 7%');
    expect(progressLabel({ phase: SYNC_PHASE.READING, projectsFound: 3 }, SYNC_KIND.CONNECT, url)).toBe('reading projects · 3 found…');
  });

  it('the bar is determinate only in the phases that carry a percent', () => {
    expect(barPercent({ phase: SYNC_PHASE.DOWNLOADING, percent: 38 })).toBe(38);
    expect(barPercent({ phase: SYNC_PHASE.RESOLVING, percent: 60 })).toBe(60);
    expect(barPercent({ phase: SYNC_PHASE.CHECKOUT, percent: 7 })).toBe(7);
    expect(barPercent({ phase: SYNC_PHASE.CONNECTING, percent: null })).toBeNull();
    expect(barPercent({ phase: SYNC_PHASE.READING, percent: 100 })).toBeNull();
  });
});
