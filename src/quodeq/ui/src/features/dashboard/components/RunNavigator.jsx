// Props: { currentRun, isLatest, isOldest, actions: { onPrev, onNext, onLatest, onView, onPrevHover, onNextHover, onLatestHover } }
// Prev/next/latest navigation buttons + current run display + optional "View run" button.
// Hover handlers (onPrevHover, etc.) are optional — when wired they prefetch the
// adjacent run's dashboard so the click feels instant.

import { t } from '../../../strings/index.js';

function RunNavPager({ currentRun, isLatest, isOldest, onPrev, onNext, onPrevHover, onNextHover }) {
  return (
    <div className="run-nav-pager">
      <button
        type="button"
        className="run-nav-btn"
        onClick={onPrev}
        onMouseEnter={onPrevHover}
        onFocus={onPrevHover}
        disabled={isOldest}
        aria-label={t('runNav.older')}
        title={t('runNav.older')}
      >
        ‹
      </button>
      <span className="run-nav-label">{currentRun}</span>
      <button
        type="button"
        className="run-nav-btn"
        onClick={onNext}
        onMouseEnter={onNextHover}
        onFocus={onNextHover}
        disabled={isLatest}
        aria-label={t('runNav.newer')}
        title={t('runNav.newer')}
      >
        ›
      </button>
    </div>
  );
}

export default function RunNavigator({
  currentRun, isLatest, isOldest,
  actions: { onPrev, onNext, onLatest, onView, onPrevHover, onNextHover, onLatestHover } = {},
}) {
  return (
    <div className="run-navigator">
      <button
        type="button"
        className="run-nav-action run-nav-action--primary"
        onClick={onLatest}
        onMouseEnter={onLatestHover}
        onFocus={onLatestHover}
        disabled={isLatest}
        title={t('runNav.latestTitle')}
      >
        {t('runNav.latest')}
      </button>

      <RunNavPager
        currentRun={currentRun} isLatest={isLatest} isOldest={isOldest}
        onPrev={onPrev} onNext={onNext} onPrevHover={onPrevHover} onNextHover={onNextHover}
      />

      {onView && (
        <button
          type="button"
          className="run-nav-action run-nav-action--outline"
          onClick={onView}
          title={t('runNav.openRunTitle')}
        >
          {t('runNav.view')}
        </button>
      )}
    </div>
  );
}
