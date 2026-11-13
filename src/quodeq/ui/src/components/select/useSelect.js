import { useRef, useState } from 'react';
import { launcherMenuPos } from '../launcher/compareLauncherMenu.js';
import { useLauncherDismiss } from '../launcher/useLauncherDismiss.js';
import { edgeEnabled, flattenOptions } from './selectOptions.js';
import { useSelectKeyboard } from './useSelectKeyboard.js';

/** Open state, the active option and the keyboard behaviour of a Select. */
export function useSelect({ value, options, onChange, disabled }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const [active, setActive] = useState(-1);
  const btnRef = useRef(null);
  const menuRef = useRef(null);
  const flat = flattenOptions(options);
  const selected = flat.findIndex((option) => option.value === (value ?? ''));

  const close = () => setOpen(false);
  useLauncherDismiss(open, btnRef, menuRef, close);

  const show = () => {
    const at = launcherMenuPos(btnRef.current);
    if (disabled || !at) return;
    setPos({ ...at, minWidth: btnRef.current.offsetWidth });
    setActive(selected >= 0 && !flat[selected].disabled ? selected : edgeEnabled(flat, 1));
    setOpen(true);
  };

  const pick = (index) => {
    const option = flat[index];
    if (!option || option.disabled) return;
    close();
    btnRef.current?.focus();
    if (option.value !== value) onChange(option.value);
  };

  const onKeyDown = useSelectKeyboard({ open, active, setActive, flat, show, close, pick });

  const toggle = () => { if (open) close(); else show(); };

  return { open, pos, active, setActive, btnRef, menuRef, flat, selected, pick, toggle, onKeyDown };
}
