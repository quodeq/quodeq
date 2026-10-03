import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('./index.js', () => ({ t: (key) => key }));
const { tRich } = await import('./rich.jsx');

function html(text) {
  return render(<p>{tRich(text)}</p>).container.firstChild.innerHTML;
}

describe('tRich', () => {
  it('returns plain text untouched', () => {
    expect(html('no markup here')).toBe('no markup here');
  });

  it('renders backtick spans as code', () => {
    expect(html('Add a `.quodeqignore` file')).toBe('Add a <code>.quodeqignore</code> file');
  });

  it('renders double-asterisk spans as strong', () => {
    expect(html('Turn on **Clean scan** now')).toBe('Turn on <strong>Clean scan</strong> now');
  });

  it('mixes both in one sentence', () => {
    expect(html('**Fix plan** or `quodeq review`')).toBe('<strong>Fix plan</strong> or <code>quodeq review</code>');
  });

  it('keeps a backtick inside bold literal', () => {
    expect(html('Press **Ctrl+`** to open')).toBe('Press <strong>Ctrl+`</strong> to open');
  });
});
