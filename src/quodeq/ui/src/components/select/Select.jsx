import { useEffect, useId } from 'react';
import { useSelect } from './useSelect.js';

const optionClass = (isActive, isSelected) => [
  'compare-dueltrigger__item q-select__option',
  isActive && 'q-select__option--active',
  isSelected && 'q-select__option--selected',
].filter(Boolean).join(' ');

function SelectMenu({ state, listId, entries }) {
  const { flat, active, selected, setActive, pick, menuRef, pos } = state;
  const optionId = (index) => `${listId}-${index}`;

  useEffect(() => {
    document.getElementById(optionId(active))?.scrollIntoView?.({ block: 'nearest' });
  });

  const renderOption = (option) => {
    const index = flat.indexOf(option);
    return (
      // tabIndex -1: focus stays on the trigger (aria-activedescendant), which owns the keyboard.
      <button
        key={option.value} id={optionId(index)} type="button" role="option" tabIndex={-1}
        aria-selected={index === selected} aria-disabled={option.disabled || undefined}
        className={optionClass(index === active, index === selected)}
        onMouseDown={(e) => e.preventDefault()}
        onMouseEnter={() => { if (!option.disabled) setActive(index); }}
        onClick={() => pick(index)}
      >
        {option.label}
      </button>
    );
  };

  // Rendered in place, not portaled: a press on an option must stay inside any
  // popover or dialog around this Select. position: fixed keeps it unclipped.
  return (
    <div id={listId} ref={menuRef} role="listbox" className="compare-dueltrigger__menu q-select__menu" style={pos}>
      {entries.map((entry) => (entry.options ? (
        <div key={entry.group} role="group" aria-label={entry.group}>
          <span className="compare-dueltrigger__hint" aria-hidden="true">{entry.group}</span>
          {entry.options.map(renderOption)}
        </div>
      ) : renderOption(entry)))}
    </div>
  );
}

/**
 * The app's dropdown. A native <select> opens a menu drawn by the OS (GTK on
 * Linux), which CSS cannot restyle, so this draws its own list in Quodeq's
 * colours and keeps the native keyboard behaviour.
 *
 * @param {string} props.value
 * @param {Array} props.options - `{value, label, disabled?}` or `{group, options}`
 * @param {(value: string) => void} props.onChange - called with the picked value
 */
export default function Select({
  id, value, options, onChange, disabled, className = '',
  'aria-label': ariaLabel, 'aria-labelledby': ariaLabelledBy,
}) {
  const listId = useId();
  const state = useSelect({ value, options, onChange, disabled });
  const { open, pos, active, selected, flat, btnRef, toggle, onKeyDown } = state;
  return (
    <>
      <button
        ref={btnRef} id={id} type="button" role="combobox" disabled={disabled}
        className={`q-select ${className}`.trim()}
        aria-label={ariaLabel} aria-labelledby={ariaLabelledBy}
        aria-haspopup="listbox" aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        onClick={toggle} onKeyDown={onKeyDown}
      >
        <span className="q-select__value">{flat[selected]?.label}</span>
        <span className="q-select__caret" aria-hidden="true">▾</span>
      </button>
      {open && pos && <SelectMenu state={state} listId={listId} entries={options} />}
    </>
  );
}
