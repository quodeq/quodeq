/**
 * GridTable — CSS-grid-based tabular layout.
 *
 * Provides the outer scaffolding; callers render rows as flat `<GridRow>`
 * children with cells in the same order as `columns`. The number of columns
 * determines the grid template.
 *
 *   <GridTable columns="2fr 1fr 1fr 80px">
 *     <GridRow header>
 *       <GridCell>Name</GridCell>
 *       ...
 *     </GridRow>
 *     <GridRow onClick={...}>
 *       <GridCell>security</GridCell>
 *       ...
 *     </GridRow>
 *   </GridTable>
 *
 * `columns` accepts any valid grid-template-columns value.
 */
import { createContext, useContext } from 'react';
import { activateOnKey } from '../../utils/a11y.js';

// Tracks whether the nearest ancestor GridRow is a header row, so GridCell
// can pick role="columnheader" vs role="cell" without every caller passing
// it down explicitly (ARIA table pattern: columnheader belongs on the cell,
// never on the row).
const GridHeaderContext = createContext(false);

/**
 * @param {object} props
 * @param {string} props.columns   Any grid-template-columns value; its track
 *   count is what fixes the number of cells a row may hold.
 * @param {boolean} [props.dense]  Tighter row padding.
 * @param {string} [props.role='table']  Override for grids that are not
 *   tabular data (e.g. role="list").
 */
export function GridTable({ columns, children, dense = false, role = 'table' }) {
  const cls = 'term-grid' + (dense ? ' term-grid--dense' : '');
  return (
    <div className={cls} role={role} style={{ '--term-grid-cols': columns }}>
      {children}
    </div>
  );
}

/**
 * @param {object} props
 * @param {boolean} [props.header]  Marks this row as a header (different styling).
 * @param {boolean} [props.muted]   De-emphasized row.
 * @param {(e: any) => void} [props.onClick]  Also makes the row focusable
 *   and keyboard-activatable.
 * @param {number} [props.ariaRowIndex]  1-based aria-rowindex, for grids whose
 *   rows are virtualized and so do not match their DOM position.
 */
export function GridRow({ header = false, muted = false, onClick, children, ariaRowIndex }) {
  const classes = ['term-grid__row'];
  if (header) classes.push('term-grid__row--header');
  if (muted) classes.push('term-grid__row--muted');
  if (onClick) classes.push('term-grid__row--clickable');
  return (
    <div
      className={classes.join(' ')}
      role="row"
      aria-rowindex={ariaRowIndex}
      onClick={onClick}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? activateOnKey(onClick) : undefined}
    >
      <GridHeaderContext.Provider value={header}>
        {children}
      </GridHeaderContext.Provider>
    </div>
  );
}

/**
 * @param {object} props
 * @param {'left'|'center'|'right'} [props.align='left']
 * @param {boolean} [props.numeric]   If true, uses tabular-nums and right-aligns by default.
 * @param {boolean} [props.muted]     De-emphasized cell.
 */
export function GridCell({ align, numeric = false, muted = false, children }) {
  const resolvedAlign = align || (numeric ? 'right' : 'left');
  const classes = ['term-grid__cell', `term-grid__cell--${resolvedAlign}`];
  if (numeric) classes.push('term-grid__cell--numeric');
  if (muted) classes.push('term-grid__cell--muted');
  const isHeader = useContext(GridHeaderContext);
  return <div className={classes.join(' ')} role={isHeader ? 'columnheader' : 'cell'}>{children}</div>;
}
