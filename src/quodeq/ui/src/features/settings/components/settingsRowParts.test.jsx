import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SettingsRowLabel, SettingsAdvanced, SettingsEnableRow } from './settingsRowParts.jsx';

describe('SettingsRowLabel', () => {
  it('wraps the label in a hint row by default', () => {
    const { container } = render(<SettingsRowLabel label="Model" description="Pick one" labelId="lbl" />);
    expect(container.innerHTML).toBe(
      '<div class="settings-row-label"><span class="settings-label-row"><span class="settings-label" id="lbl">Model</span></span>'
      + '<span class="settings-description">Pick one</span></div>',
    );
  });

  it('renders the bare label and description when the row has no hint slot', () => {
    const { container } = render(<SettingsRowLabel label="Power" description="How hard" hintSlot={false} />);
    expect(container.innerHTML).toBe(
      '<div class="settings-row-label"><span class="settings-label">Power</span>'
      + '<span class="settings-description">How hard</span></div>',
    );
  });
});

describe('SettingsAdvanced', () => {
  it('puts its children in the collapsible advanced block', () => {
    const { container } = render(<SettingsAdvanced><p>inner</p></SettingsAdvanced>);
    expect(container.innerHTML).toBe(
      '<details class="settings-advanced"><summary class="settings-advanced-toggle">Advanced</summary>'
      + '<div class="settings-advanced-content"><p>inner</p></div></details>',
    );
  });
});

describe('SettingsEnableRow', () => {
  it('is the last row while disabled and offers On/Off tabs', () => {
    const onChange = vi.fn();
    const { container } = render(<SettingsEnableRow enabled={false} setEnabled={onChange} label="Feature" description="Turns it on" />);
    expect(container.firstChild.className).toBe('settings-row settings-row--last');
    expect(screen.getByRole('tab', { name: 'Off' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('tab', { name: 'On' }));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('leaves room for the rows below while enabled', () => {
    const { container } = render(<SettingsEnableRow enabled setEnabled={() => {}} label="Feature" description="Turns it on" />);
    expect(container.firstChild.className).toBe('settings-row');
    expect(screen.getByRole('tab', { name: 'On' })).toHaveAttribute('aria-selected', 'true');
  });
});
