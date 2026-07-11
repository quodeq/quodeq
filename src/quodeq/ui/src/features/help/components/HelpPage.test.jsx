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

describe('HelpPage violations section', () => {
  it('describes the real sub-tabs', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Violations & Fix Plans' }));
    expect(screen.getByText('by-dimension')).toBeInTheDocument();
    expect(screen.getByText('by-file')).toBeInTheDocument();
    expect(screen.queryByText(/Heatgrid/)).toBeNull();
  });
});
