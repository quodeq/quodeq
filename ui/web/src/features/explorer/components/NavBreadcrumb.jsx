import { Fragment } from 'react';

export default function NavBreadcrumb({ stack, onBack, onGoTo }) {
  if (stack.length <= 1) return null;

  const segments = stack.map((entry, i) => {
    let label;
    switch (entry.page) {
      case 'overview':      label = 'Overview'; break;
      case 'run':           label = entry.label || entry.runId || 'Run'; break;
      case 'explorer':      label = entry.dimension
        ? entry.dimension.charAt(0).toUpperCase() + entry.dimension.slice(1)
        : 'Dimension'; break;
      case 'violation':     label = entry.label || entry.principle?.name || 'Violation'; break;
      case 'evaluate':      label = 'Evaluate'; break;
      case 'file':          label = entry.label || 'File Detail'; break;
      case 'principle':     label = entry.label || 'Principle Detail'; break;
      case 'evalprinciple': label = entry.label || entry.principleName || 'Principle'; break;
      default:              label = entry.label || entry.page;
    }
    return { label, index: i };
  });

  return (
    <nav className="nav-breadcrumb">
      <button className="nav-back-btn" onClick={onBack} title="Go back">
        ‹
      </button>
      <div className="nav-crumbs">
        {segments.map((seg, i) => (
          <Fragment key={i}>
            {i > 0 && <span className="nav-crumb-sep">›</span>}
            <button
              className={`nav-crumb-btn${i === segments.length - 1 ? ' active' : ''}`}
              onClick={() => onGoTo(seg.index)}
              disabled={i === segments.length - 1}
            >
              {seg.label}
            </button>
          </Fragment>
        ))}
      </div>
    </nav>
  );
}
