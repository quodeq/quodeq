import { useEffect, useReducer } from 'react';
import { deriveRunElapsedS, msUntilNextSecond } from '../components/buildJobStatCells.js';

/**
 * The evaluate screen's elapsed clock, in seconds. Server-anchored (see
 * deriveRunElapsedS) and ticking once per second while the job runs, so
 * every consumer — the stat strip's ELAPSED tile and the progress footer —
 * reads the exact same value and can never drift apart.
 *
 * Ticks are aligned to the whole-second boundary of the *elapsed* value
 * (msUntilNextSecond): a fixed 1s interval has its phase fixed at mount and
 * beats against the boundary, producing visible double/skip ticks.
 *
 * @param {object|null} job — needs status, startedAt, endedAt
 * @param {object|null} progress — the polled progress payload (totalElapsedS)
 * @param {number|undefined} dataUpdatedAt — react-query's timestamp for when
 *   that payload landed; the extrapolation base between polls
 * @returns {number|null} elapsed seconds, null while unknowable
 */
export function useRunElapsed(job, progress, dataUpdatedAt) {
  const running = job?.status === 'running';
  const [, bump] = useReducer((t) => t + 1, 0);

  const elapsedS = deriveRunElapsedS({
    running,
    serverElapsedS: progress?.totalElapsedS,
    serverUpdatedAtMs: dataUpdatedAt,
    nowMs: Date.now(),
    startedAt: job?.startedAt,
    endedAt: job?.endedAt,
  });

  const serverElapsedS = progress?.totalElapsedS;
  const startedAt = job?.startedAt;
  const active = running && elapsedS != null;
  useEffect(() => {
    if (!active) return undefined;
    // Virtual start of the run on the client's clock: the display flips when
    // floor((now - anchor) / 1000) changes, matching deriveRunElapsedS.
    const anchorMs = Number.isFinite(serverElapsedS) && Number.isFinite(dataUpdatedAt)
      ? dataUpdatedAt - serverElapsedS * 1000
      : Date.parse(startedAt);
    if (Number.isNaN(anchorMs)) return undefined;
    let id;
    const schedule = () => {
      id = setTimeout(() => { bump(); schedule(); }, msUntilNextSecond(Date.now() - anchorMs));
    };
    schedule();
    return () => clearTimeout(id);
  }, [active, serverElapsedS, dataUpdatedAt, startedAt]);

  return elapsedS;
}
