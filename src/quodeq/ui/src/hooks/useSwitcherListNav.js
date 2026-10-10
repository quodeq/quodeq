import { useMemo, useState } from 'react';
import { KEY } from '../vocab/keyboard.js';
import { filterSwitcherRows } from '../features/explorer/components/projectSwitcherModel.js';

/**
 * The project switcher's search and keyboard state: the typed query, the
 * rows it leaves, and which row ArrowUp/ArrowDown has highlighted. The
 * highlight starts on the current project and returns to the top on every
 * new query. Mount it inside the open popover so each opening starts clean.
 * @param {Array<{id: string}>} rows - every switcher row (see buildSwitcherRows)
 * @param {string|null} currentId - the active project's id
 * @param {(row: object) => void} onPick - Enter on a row
 */
export function useSwitcherListNav(rows, currentId, onPick) {
  const [query, setQueryState] = useState('');
  const [active, setActive] = useState(() => Math.max(0, rows.findIndex((r) => r.id === currentId)));
  const visible = useMemo(() => filterSwitcherRows(rows, query), [rows, query]);
  const activeIndex = Math.min(active, Math.max(0, visible.length - 1));

  const setQuery = (q) => { setQueryState(q); setActive(0); };

  const onKeyDown = (e) => {
    if (e.key === KEY.ARROW_DOWN || e.key === KEY.ARROW_UP) {
      e.preventDefault();
      if (visible.length === 0) return;
      const step = e.key === KEY.ARROW_DOWN ? 1 : -1;
      setActive((activeIndex + step + visible.length) % visible.length);
    } else if (e.key === KEY.ENTER) {
      e.preventDefault();
      if (visible[activeIndex]) onPick(visible[activeIndex]);
    }
  };

  return { query, setQuery, visible, activeIndex, setActive, onKeyDown };
}
