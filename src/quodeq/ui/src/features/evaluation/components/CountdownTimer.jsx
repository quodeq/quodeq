import { useEffect, useState } from 'react';

const ALERT_THRESHOLD_S = 30;
const TICK_MS = 500;
const TERMINAL_PHASES = new Set(['done', 'failed', 'cancelled', 'lost']);

function format(seconds) {
  const safe = Math.max(0, Math.floor(seconds));
  const m = Math.floor(safe / 60);
  const s = safe % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function CountdownTimer({ deadlineAt, budgetSeconds, phase }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!deadlineAt) return undefined;
    const id = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(id);
  }, [deadlineAt]);

  if (TERMINAL_PHASES.has(phase)) return null;
  // Unlimited means there is nothing to count. A run can still carry a
  // deadline while the configured limit is Unlimited (it was started under a
  // limit, or it is a CLI run the Evaluate tab adopted), and counting that
  // stale deadline down reads as "my unlimited run is about to be cut off".
  const unlimited = !budgetSeconds || budgetSeconds <= 0;
  if (unlimited) return null;

  if (!deadlineAt) {
    return (
      <span className="eval-countdown eval-countdown--idle" data-testid="eval-countdown">
        {format(budgetSeconds)}
      </span>
    );
  }

  const remainingS = Math.max(0, (new Date(deadlineAt).getTime() - now) / 1000);
  const alert = remainingS <= ALERT_THRESHOLD_S;
  return (
    <span
      className={`eval-countdown${alert ? ' eval-countdown--alert' : ''}`}
      data-testid="eval-countdown"
    >
      {format(remainingS)}
    </span>
  );
}
