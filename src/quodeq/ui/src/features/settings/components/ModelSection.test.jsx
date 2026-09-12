import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
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

// Cluster 19 — handleModelChange had no try/catch at all, so a throwing
// storage.setItem (e.g. QuotaExceededError in private browsing) would escape
// this React onChange handler.
describe('ModelSection — handleModelChange storage guard', () => {
  it('does not throw when storage.setItem throws, and still updates the field', () => {
    // Replace the whole global rather than spying on `localStorage.setItem`:
    // when JSDOM supplies a real Storage, its proxy swallows the added own
    // property and the spy never takes effect (green locally, red in CI).
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {
        throw new DOMException('QuotaExceededError');
      },
      removeItem: () => {},
      clear: () => {},
    });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const onFastChange = vi.fn();
    const aiCmd = { value: 'claude', onApply: () => {} };

    const { getAllByRole } = render(
      <ModelSection
        aiCmd={aiCmd}
        models={{ ...stubModels, onFastChange }}
        availableClients={[]}
      />
    );

    const fastInput = getAllByRole('textbox').find((el) => el.id === 'model-override-1');
    expect(() => fireEvent.change(fastInput, { target: { value: 'new-model' } })).not.toThrow();
    expect(onFastChange).toHaveBeenCalledWith('new-model');
    expect(warn).toHaveBeenCalled();

    vi.unstubAllGlobals();
    warn.mockRestore();
  });
});
