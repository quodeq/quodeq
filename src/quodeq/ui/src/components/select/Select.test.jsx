import { useRef, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import Select from './Select.jsx';
import { useDismissOnOutside } from '../../hooks/useDismissOnOutside.js';

const OPTIONS = [
  { value: '', label: 'Pick a model' },
  { value: 'opus', label: 'Opus' },
  { value: 'old', label: 'Old', disabled: true },
  { value: 'sonnet', label: 'Sonnet' },
];

function renderSelect(props = {}) {
  const onChange = vi.fn();
  render(<Select aria-label="Model" value="opus" options={OPTIONS} onChange={onChange} {...props} />);
  return { onChange, trigger: screen.getByRole('combobox', { name: 'Model' }) };
}

const press = (el, key) => fireEvent.keyDown(el, { key });
const activeOption = (trigger) => document.getElementById(trigger.getAttribute('aria-activedescendant'));

describe('Select: closed', () => {
  it('shows the selected label and keeps the list out of the page', () => {
    const { trigger } = renderSelect();
    expect(trigger).toHaveTextContent('Opus');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('does not open while disabled', () => {
    const { trigger } = renderSelect({ disabled: true });
    expect(trigger).toBeDisabled();
    fireEvent.click(trigger);
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('can be named by a label element', () => {
    render(
      <>
        <label htmlFor="m">Model field</label>
        <Select id="m" value="opus" options={OPTIONS} onChange={() => {}} />
      </>,
    );
    expect(screen.getByRole('combobox', { name: 'Model field' })).toHaveTextContent('Opus');
  });
});

describe('Select: picking with the pointer', () => {
  it('reports the picked value, closes, and keeps focus on the trigger', () => {
    const { trigger, onChange } = renderSelect();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('option', { name: 'Sonnet' }));
    expect(onChange).toHaveBeenCalledWith('sonnet');
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it('marks the current option and ignores a disabled one', () => {
    const { trigger, onChange } = renderSelect();
    fireEvent.click(trigger);
    expect(screen.getByRole('option', { name: 'Opus' })).toHaveAttribute('aria-selected', 'true');
    const old = screen.getByRole('option', { name: 'Old' });
    expect(old).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(old);
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('does not report a pick of the current value', () => {
    const { trigger, onChange } = renderSelect();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('option', { name: 'Opus' }));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('closes on a press outside', () => {
    const { trigger } = renderSelect();
    fireEvent.click(trigger);
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('renders named groups', () => {
    const groups = [
      { group: 'Latest', options: [{ value: 'a', label: 'A' }] },
      { group: 'Pinned', options: [{ value: 'b', label: 'B' }] },
    ];
    const { trigger } = renderSelect({ value: 'b', options: groups });
    expect(trigger).toHaveTextContent('B');
    fireEvent.click(trigger);
    const pinned = screen.getByRole('group', { name: 'Pinned' });
    expect(pinned).toContainElement(screen.getByRole('option', { name: 'B' }));
  });
});

describe('Select: keyboard', () => {
  it.each(['ArrowDown', 'ArrowUp', 'Enter', ' '])('%j opens on the current option', (key) => {
    const { trigger } = renderSelect();
    press(trigger, key);
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(activeOption(trigger)).toHaveTextContent('Opus');
  });

  it('arrows skip disabled options and stop at the ends', () => {
    const { trigger } = renderSelect();
    press(trigger, 'ArrowDown');
    press(trigger, 'ArrowDown');
    expect(activeOption(trigger)).toHaveTextContent('Sonnet');
    press(trigger, 'ArrowDown');
    expect(activeOption(trigger)).toHaveTextContent('Sonnet');
    press(trigger, 'ArrowUp');
    expect(activeOption(trigger)).toHaveTextContent('Opus');
  });

  it('Home and End jump to the first and last enabled option', () => {
    const { trigger } = renderSelect();
    press(trigger, 'Enter');
    press(trigger, 'End');
    expect(activeOption(trigger)).toHaveTextContent('Sonnet');
    press(trigger, 'Home');
    expect(activeOption(trigger)).toHaveTextContent('Pick a model');
  });

  it.each(['Enter', ' '])('%j picks the active option', (key) => {
    const { trigger, onChange } = renderSelect();
    press(trigger, 'Enter');
    press(trigger, 'End');
    press(trigger, key);
    expect(onChange).toHaveBeenCalledWith('sonnet');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('Tab closes without picking', () => {
    const { trigger, onChange } = renderSelect();
    press(trigger, 'Enter');
    press(trigger, 'End');
    press(trigger, 'Tab');
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('typing jumps to a matching enabled option', () => {
    const { trigger } = renderSelect();
    press(trigger, 'Enter');
    press(trigger, 's');
    expect(activeOption(trigger)).toHaveTextContent('Sonnet');
    press(trigger, 'o');
    expect(activeOption(trigger)).toHaveTextContent('Sonnet');
  });
});

function InPopover({ onClosePopover }) {
  const panel = useRef(null);
  const [value, setValue] = useState('opus');
  useDismissOnOutside(true, panel, onClosePopover);
  return (
    <div ref={panel}>
      <Select aria-label="Model" value={value} options={OPTIONS} onChange={setValue} />
    </div>
  );
}

describe('Select: inside a dismissable popover', () => {
  it('Escape closes only the list, then the popover', () => {
    const onClosePopover = vi.fn();
    render(<InPopover onClosePopover={onClosePopover} />);
    const trigger = screen.getByRole('combobox');
    press(trigger, 'Enter');
    press(trigger, 'Escape');
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(onClosePopover).not.toHaveBeenCalled();
    press(trigger, 'Escape');
    expect(onClosePopover).toHaveBeenCalledTimes(1);
  });

  it('a press on an option does not count as outside the popover', () => {
    const onClosePopover = vi.fn();
    render(<InPopover onClosePopover={onClosePopover} />);
    const trigger = screen.getByRole('combobox');
    fireEvent.click(trigger);
    const option = screen.getByRole('option', { name: 'Sonnet' });
    fireEvent.mouseDown(option);
    fireEvent.click(option);
    expect(onClosePopover).not.toHaveBeenCalled();
    expect(trigger).toHaveTextContent('Sonnet');
  });
});
