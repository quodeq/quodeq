import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import ModelSection from './ModelSection.jsx';

const stubModels = {
  aiModel: '',
  onAiModelChange: () => {},
  fast: '',
  onFastChange: () => {},
  balanced: '',
  onBalancedChange: () => {},
  thorough: '',
  onThoroughChange: () => {},
};

// Finding #213 — ClientSelector (and ModelSettings) destructures aiCmd without a default;
// passing undefined throws immediately on `const { value, onApply } = aiCmd`.
describe('ModelSection — finding #213 (aiCmd undefined)', () => {
  it('renders without throwing when aiCmd is undefined', () => {
    expect(() =>
      render(
        <ModelSection
          aiCmd={undefined}
          models={stubModels}
          availableClients={[]}
        />
      )
    ).not.toThrow();
  });
});

// Finding #214 — ClientSelector checks `availableClients === null` but not undefined,
// so calling `.filter()` on undefined throws a TypeError.
describe('ModelSection — finding #214 (availableClients undefined)', () => {
  it('renders without throwing when availableClients is undefined', () => {
    const aiCmd = { value: null, onApply: () => {} };
    expect(() =>
      render(
        <ModelSection
          aiCmd={aiCmd}
          models={stubModels}
          availableClients={undefined}
        />
      )
    ).not.toThrow();
  });
});
