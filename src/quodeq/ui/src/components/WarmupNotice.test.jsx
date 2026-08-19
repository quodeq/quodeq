import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import WarmupNotice from './WarmupNotice.jsx';

describe('WarmupNotice', () => {
  it('renders nothing when warm-up is inactive or absent', () => {
    expect(render(<WarmupNotice warmup={null} />).container.firstChild).toBeNull();
    expect(render(<WarmupNotice warmup={{ active: false, projectsDone: 2, projectsTotal: 2 }} />).container.firstChild).toBeNull();
  });

  it('shows determinate progress with the current project name', () => {
    const { container, getByText } = render(
      <WarmupNotice warmup={{ active: true, projectsDone: 1, projectsTotal: 6, currentProjectName: 'my-app' }} />,
    );
    expect(getByText(/Project 2 of 6: my-app/)).toBeInTheDocument();
    expect(container.querySelector('.warmup-notice__fill').style.width).toBe('17%');
  });

  it('falls back to the unnamed label when no current project name', () => {
    const { getByText } = render(
      <WarmupNotice warmup={{ active: true, projectsDone: 0, projectsTotal: 3, currentProjectName: null }} />,
    );
    expect(getByText(/Project 1 of 3$/)).toBeInTheDocument();
  });
});
