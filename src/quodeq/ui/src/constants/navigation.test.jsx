import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ICON_STANDARDS, ICON_STAR_OUTLINE, ICON_STAR_FILLED } from './navigation.jsx';

const pathOf = (icon) => render(icon).container.querySelector('path').getAttribute('d');

describe('navigation star icons', () => {
  it('draws the same star outline in the standards and star icons', () => {
    const d = 'M12 2l3 7h7l-5.5 4 2 7L12 16l-6.5 4 2-7L2 9h7l3-7z';
    expect(pathOf(ICON_STANDARDS)).toBe(d);
    expect(pathOf(ICON_STAR_OUTLINE)).toBe(d);
    expect(pathOf(ICON_STAR_FILLED)).toBe(d);
  });

  it('keeps the filled star filled and the other two unfilled', () => {
    const fillOf = (icon) => render(icon).container.querySelector('svg').getAttribute('fill');
    expect(fillOf(ICON_STANDARDS)).toBe('none');
    expect(fillOf(ICON_STAR_OUTLINE)).toBe('none');
    expect(fillOf(ICON_STAR_FILLED)).toBe('currentColor');
  });
});
