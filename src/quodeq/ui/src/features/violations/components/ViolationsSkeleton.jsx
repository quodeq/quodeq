// Footprint stand-in for the loaded violations page, shown while the
// dimension data is loading (and while an error-retry is in flight). The
// floating inline spinner it replaces reserved no height, so the sub-tab
// pills and dimension groups popped in below the header when data landed.
// Rides the real .violations-flag-row for the pill row's spacing; the
// groups are representative (3 groups of a header + two card rows) since
// the real dimension count varies per project. House skeleton idiom:
// static dimmed blocks, no shimmer, no spinner.

const GROUP_COUNT = 3;
const PILL_COUNT = 3;

export default function ViolationsSkeleton() {
  return (
    <div className="violations-skeleton" aria-busy="true" aria-hidden="true">
      <div className="violations-flag-row">
        {Array.from({ length: PILL_COUNT }, (_, index) => (
          <span key={index} className="violations-skeleton__bar violations-skeleton__pill" />
        ))}
      </div>
      {Array.from({ length: GROUP_COUNT }, (_, index) => (
        <div key={index} className="violations-skeleton__group">
          <span className="violations-skeleton__bar violations-skeleton__bar--group-header" />
          <span className="violations-skeleton__bar violations-skeleton__bar--card" />
          <span className="violations-skeleton__bar violations-skeleton__bar--card" />
        </div>
      ))}
    </div>
  );
}
