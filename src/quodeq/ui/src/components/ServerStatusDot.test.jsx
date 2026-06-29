import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ServerStatusDot from './ServerStatusDot.jsx';

describe('ServerStatusDot', () => {
  it('renders a green dot with the address in the tooltip when connected', () => {
    render(<ServerStatusDot connected url="http://127.0.0.1:7863" />);
    const el = screen.getByRole('img', { name: 'Server running · 127.0.0.1:7863' });
    expect(el).toHaveAttribute('title', 'Server running · 127.0.0.1:7863');
    expect(el.querySelector('.topbar-dot--ok')).not.toBeNull();
  });

  it('strips the scheme from https urls too', () => {
    render(<ServerStatusDot connected url="https://localhost:7863" />);
    expect(screen.getByRole('img', { name: 'Server running · localhost:7863' })).toBeInTheDocument();
  });

  it('omits the address when no url is provided', () => {
    render(<ServerStatusDot connected url={null} />);
    expect(screen.getByRole('img', { name: 'Server running' })).toBeInTheDocument();
  });

  it('renders a red dot labelled offline when not connected', () => {
    render(<ServerStatusDot connected={false} url="http://127.0.0.1:7863" />);
    const el = screen.getByRole('img', { name: 'Server offline' });
    expect(el.querySelector('.topbar-dot--err')).not.toBeNull();
  });

  it('renders nothing until the status is known', () => {
    const { container } = render(<ServerStatusDot connected={null} />);
    expect(container.firstChild).toBeNull();
  });
});
