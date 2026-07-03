import { describe, it, expect, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HelpFigure from './HelpFigure.jsx';

afterEach(() => {
  document.documentElement.removeAttribute('data-theme');
});

describe('HelpFigure screenshot mode', () => {
  it('picks the dark asset when the applied theme is dark', () => {
    document.documentElement.setAttribute('data-theme', 'dark');
    render(
      <HelpFigure caption="The editor" srcDark="/d.webp" srcLight="/l.webp" alt="Editor view" />
    );
    expect(screen.getByAltText('Editor view')).toHaveAttribute('src', '/d.webp');
  });

  it('picks the light asset when the applied theme is light', () => {
    document.documentElement.setAttribute('data-theme', 'light');
    render(
      <HelpFigure caption="The editor" srcDark="/d.webp" srcLight="/l.webp" alt="Editor view" />
    );
    expect(screen.getByAltText('Editor view')).toHaveAttribute('src', '/l.webp');
  });

  it('lazy-loads the image and renders the caption', () => {
    document.documentElement.setAttribute('data-theme', 'dark');
    render(
      <HelpFigure caption="The editor" srcDark="/d.webp" srcLight="/l.webp" alt="Editor view" />
    );
    expect(screen.getByAltText('Editor view')).toHaveAttribute('loading', 'lazy');
    expect(screen.getByText('The editor')).toBeInTheDocument();
  });
});

describe('HelpFigure illustration mode', () => {
  it('hides the art from assistive tech and describes via the caption', () => {
    render(
      <HelpFigure caption="Severity weights bend the curve">
        <svg data-testid="art" />
      </HelpFigure>
    );
    expect(screen.getByTestId('art').closest('[aria-hidden="true"]')).not.toBeNull();
    expect(screen.getByText('Severity weights bend the curve')).toBeInTheDocument();
  });

  it('renders its children', () => {
    render(
      <HelpFigure caption="c"><span data-testid="art" /></HelpFigure>
    );
    expect(screen.getByTestId('art')).toBeInTheDocument();
  });

  it('introduces no focusable elements', () => {
    const { container } = render(
      <HelpFigure caption="c"><svg data-testid="art" /></HelpFigure>
    );
    expect(container.querySelector('[tabindex]')).toBeNull();
  });
});

describe('HelpFigure focus safety', () => {
  it('introduces no focusable elements', () => {
    const { container } = render(
      <HelpFigure caption="c" srcDark="/d.webp" srcLight="/l.webp" alt="a" />
    );
    expect(container.querySelector('[tabindex]')).toBeNull();
  });
});
