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
    expect(screen.getByText('SEVERITY')).toBeInTheDocument();
    expect(screen.getByText(/RESET Q²/)).toBeInTheDocument();
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
  it('describes majors, open types, density and the since-baseline panel', () => {
    render(<HelpPage initialSection="overview" />);
    for (const name of ['Majors', 'Open types', 'Density', 'Since baseline']) {
      expect(screen.getAllByText(name, { exact: false }).length).toBeGreaterThan(0);
    }
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

describe('HelpPage history majors and open types', () => {
  it('documents the count series, the table columns and the since-baseline panel', () => {
    const { container } = render(<HelpPage initialSection="history" />);
    expect(screen.getByRole('heading', { level: 3, name: /Since the baseline/ })).toBeInTheDocument();
    expect((container.textContent.match(/majors/gi) || []).length).toBeGreaterThan(1);
    expect((container.textContent.match(/open types/gi) || []).length).toBeGreaterThan(1);
  });

  it('describes the report order on the Overview page', () => {
    render(<HelpPage initialSection="overview" />);
    expect(screen.getByText(/leads with the same numbers as the header/)).toBeInTheDocument();
  });
});
