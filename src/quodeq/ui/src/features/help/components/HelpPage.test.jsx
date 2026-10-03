import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HelpPage from './HelpPage.jsx';

// BrandCarousel auto-advances on a timer; stub it out for determinism.
vi.mock('../../../components/BrandCarousel.jsx', () => ({
  default: () => null,
}));

describe('HelpPage grade formula section', () => {
  it('lists Grade Formula in the section nav right after History & Trends', () => {
    render(<HelpPage />);
    const nav = screen.getByRole('button', { name: 'Grade Formula' });
    expect(nav.previousSibling).toHaveTextContent('History & Trends');
  });

  it('renders the Grade Formula section when selected', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Grade Formula' }));
    expect(screen.getByRole('heading', { level: 2, name: 'Grade Formula' })).toBeInTheDocument();
    expect(screen.getByText('FORMULA')).toBeInTheDocument();
    expect(screen.getByText('TYPES')).toBeInTheDocument();
    expect(screen.getByText(/RESET Q²/)).toBeInTheDocument();
    expect(screen.queryByText('SEVERITY')).not.toBeInTheDocument();
  });
});

describe('HelpPage why this grade section', () => {
  it('is prose only and points at the editor for the live numbers', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Why This Grade' }));
    expect(screen.getByRole('heading', { level: 2, name: 'Why This Grade' })).toBeInTheDocument();
    expect(screen.getByText(/shows these stages on your own run/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Principle')).not.toBeInTheDocument();
    expect(screen.queryByText(/Open a project with a finished run/)).not.toBeInTheDocument();
  });
});

describe('HelpPage history section', () => {
  it('documents day, week, month score grouping', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'History & Trends' }));
    expect(screen.getByRole('heading', { level: 3, name: /Group the Overview chart by day, week, or month/ })).toBeInTheDocument();
  });
});

describe('HelpPage providers section', () => {
  it('documents the omlx provider', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'AI Providers' }));
    expect(screen.getByRole('heading', { level: 3, name: /omlx \(Apple Silicon only\)/ })).toBeInTheDocument();
  });

  it('documents the llama.cpp provider', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'AI Providers' }));
    expect(screen.getByRole('heading', { level: 3, name: /llama\.cpp \(local, GGUF models\)/ })).toBeInTheDocument();
  });
});

describe('HelpPage settings section', () => {
  it('documents update notifications', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
    expect(screen.getByRole('heading', { level: 3, name: 'Updates' })).toBeInTheDocument();
    expect(screen.getByText(/QUODEQ_NO_UPDATE_NOTIFIER/)).toBeInTheDocument();
  });
});

describe('HelpPage overview section', () => {
  it('lists Overview in the section nav right after Running Evaluations', () => {
    render(<HelpPage />);
    const nav = screen.getByRole('button', { name: 'Overview' });
    expect(nav.previousSibling).toHaveTextContent('Running Evaluations');
  });

  it('documents accumulated scores and the report', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
    expect(screen.getByRole('heading', { level: 2, name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Accumulated scores' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'The report' })).toBeInTheDocument();
  });
});

describe('HelpPage command line section', () => {
  it('documents the CLI commands and PR review flow', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Command Line & CI' }));
    expect(screen.getByRole('heading', { level: 2, name: 'Command Line & CI' })).toBeInTheDocument();
    expect(screen.getAllByText('quodeq review').length).toBeGreaterThan(0);
    expect(screen.getAllByText('quodeq export sarif').length).toBeGreaterThan(0);
    expect(screen.getByText(/--diff-from/)).toBeInTheDocument();
  });
});

describe('HelpPage shared repository section', () => {
  it('lists Shared Repository in the section nav right after Projects', () => {
    render(<HelpPage />);
    const nav = screen.getByRole('button', { name: 'Shared Repository' });
    expect(nav.previousSibling).toHaveTextContent('Projects');
  });

  it('documents connect, publish, pull, and the cache override', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Shared Repository' }));
    expect(screen.getByRole('heading', { level: 2, name: 'Shared Repository' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Publishing' })).toBeInTheDocument();
    expect(screen.getByText('pull local copy')).toBeInTheDocument();
    expect(screen.getByText(/QUODEQ_CACHE_ROOT/)).toBeInTheDocument();
  });

  it('cross-references sharing from the Projects section', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Projects' }));
    expect(screen.getByText('Publish / update')).toBeInTheDocument();
    expect(screen.getByText('Pull local copy')).toBeInTheDocument();
  });
});

describe('HelpPage violations section', () => {
  it('describes the real sub-tabs', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Violations & Fix Plans' }));
    expect(screen.getByText('by-dimension')).toBeInTheDocument();
    expect(screen.getByText('by-file')).toBeInTheDocument();
    expect(screen.queryByText(/Heatgrid/)).toBeNull();
  });
});

describe('HelpPage deep link', () => {
  it('opens on the requested section', () => {
    render(<HelpPage initialSection="grade-formula" />);
    expect(screen.getByRole('heading', { level: 2, name: 'Grade Formula' })).toBeInTheDocument();
  });

  it('falls back to philosophy on an unknown section', () => {
    render(<HelpPage initialSection="nope" />);
    expect(screen.getByRole('button', { name: 'Philosophy' })).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('HelpPage grade formula parameters', () => {
  it('documents every on-the-fly parameter', () => {
    render(<HelpPage initialSection="grade-formula" />);
    for (const name of ['Severity weights', 'Strictness K', 'Lift compress', 'Ceiling scale', 'Severity floors', 'Grade thresholds', 'Dimension weights']) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
  });
});

describe('HelpPage overview header stats', () => {
  it('describes the badges, the ratio and the density, and no since-baseline panel', () => {
    render(<HelpPage initialSection="overview" />);
    for (const name of ['MAJ badges', 'Density']) {
      expect(screen.getAllByText(name, { exact: false }).length).toBeGreaterThan(0);
    }
    expect(screen.queryAllByText('Since baseline', { exact: false })).toHaveLength(0);
  });
});

describe('HelpPage violations by type', () => {
  it('documents the by-type sub-tab and dismissing a type', () => {
    render(<HelpPage initialSection="violations" />);
    expect(screen.getByRole('heading', { level: 3, name: /Four sub-tabs, one dataset/ })).toBeInTheDocument();
    expect(screen.getAllByText(/by-type/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Dismiss all/).length).toBeGreaterThan(0);
  });
});

describe('HelpPage overview: the four tiles', () => {
  it('documents the chips\' arrows, the ratio reading and density in the tile, and no strip', () => {
    const { container } = render(<HelpPage initialSection="overview" />);
    expect(screen.queryByRole('heading', { level: 3, name: /The strip/ })).not.toBeInTheDocument();
    expect(container.textContent).toMatch(/change since the baseline run/);
    expect(container.textContent).toMatch(/violations to compliance/);
    expect(container.textContent).toMatch(/per 100 files read/);
    expect(container.textContent).not.toMatch(/Open types|see findings/);
  });
});

describe('HelpPage history counts', () => {
  it('documents the tooltip counts and the MAJORS and TYPES columns, without lines, legend or a since-baseline panel', () => {
    const { container } = render(<HelpPage initialSection="history" />);
    expect((container.textContent.match(/majors/gi) || []).length).toBeGreaterThan(1);
    expect((container.textContent.match(/open types/gi) || []).length).toBeGreaterThan(1);
    expect(container.textContent).toMatch(/criticals/i);
    expect(screen.queryByRole('heading', { level: 3, name: /Since the baseline/ })).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/legend|dashed|dotted|per-dimension lines/i);
  });

  it('describes the report order on the Overview page', () => {
    render(<HelpPage initialSection="overview" />);
    expect(screen.getByText(/report opens with the header's numbers/)).toBeInTheDocument();
  });
});
