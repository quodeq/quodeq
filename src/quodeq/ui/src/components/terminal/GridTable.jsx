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
 * @param {(e: any) => void} [props.onClick]
 */
export function GridRow({ header = false, muted = false, onClick, children, ariaRowIndex }) {
  const classes = ['term-grid__row'];
  if (header) classes.push('term-grid__row--header');
  if (muted) classes.push('term-grid__row--muted');
  if (onClick) classes.push('term-grid__row--clickable');
  const role = header ? 'columnheader' : 'row';
  return (
    <div
      className={classes.join(' ')}
      role={role}
      aria-rowindex={ariaRowIndex}
      onClick={onClick}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter') onClick(e); } : undefined}
    >
      {children}
    </div>
  );
}

/**
 * @param {object} props
 * @param {'left'|'center'|'right'} [props.align='left']
 * @param {boolean} [props.numeric]   If true, uses tabular-nums and right-aligns by default.
 */
export function GridCell({ align, numeric = false, muted = false, children }) {
  const resolvedAlign = align || (numeric ? 'right' : 'left');
  const classes = ['term-grid__cell', `term-grid__cell--${resolvedAlign}`];
  if (numeric) classes.push('term-grid__cell--numeric');
  if (muted) classes.push('term-grid__cell--muted');
  return <div className={classes.join(' ')} role="cell">{children}</div>;
}
