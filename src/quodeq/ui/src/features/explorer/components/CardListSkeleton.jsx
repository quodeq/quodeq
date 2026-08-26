// Fallback for DeferredMount on the detail pages' card lists. The inline
// LoadingScreen it replaces is position:absolute and reserves zero height,
// so the page jumped from shell-only to full list height when the
// VirtualList mounted (and the spinner overlaid the page from the top of
// main.dashboard, not the list slot). These bars stand in the list's slot
// with a card-like footprint instead: one 36px section-header row plus
// 160px card rows, matching the pages' estimateItemSize. House skeleton
// idiom: static dimmed blocks, no shimmer, no spinner.

const DEFAULT_ROW_COUNT = 4;

export default function CardListSkeleton({ rows = DEFAULT_ROW_COUNT }) {
  return (
    <div className="card-list-skeleton" aria-busy="true" aria-hidden="true">
      <span className="card-list-skeleton__bar card-list-skeleton__bar--header" />
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} className="card-list-skeleton__bar card-list-skeleton__bar--card" />
      ))}
    </div>
  );
}
