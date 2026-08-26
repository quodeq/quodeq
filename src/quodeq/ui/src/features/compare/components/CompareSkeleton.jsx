// Pre-projectsLoaded stand-in for the fleet table, replacing the bare
// "loading comparison…" text line. Once projects load the page renders
// immediately and rows fill in progressively (per-row pending marks), so
// this only covers the initial wait. House skeleton idiom: static dimmed
// blocks, no shimmer, no spinner.

const ROW_COUNT = 5;

export default function CompareSkeleton() {
  return (
    <div className="compare-skeleton" aria-busy="true" aria-hidden="true">
      <span className="compare-skeleton__bar compare-skeleton__bar--header" />
      {Array.from({ length: ROW_COUNT }, (_, index) => (
        <span key={index} className="compare-skeleton__bar compare-skeleton__bar--row" />
      ))}
    </div>
  );
}
