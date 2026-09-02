/** The sibling-choice menu shared by both segment shapes below: a plain
 * list of radio-style items, current one marked, styled as a choice (not a
 * path — that's the ellipsis menu). */
function SiblingMenu({ siblings, seg, onGoTo, setOpenKey }) {
  return (
    <div className="nav-breadcrumb__menu nav-breadcrumb__menu--siblings" role="menu" aria-label={`Switch ${seg.label}`}>
      {siblings.map((item) => (
        <button
          key={item.key}
          type="button"
          role="menuitemradio"
          aria-checked={!!item.current}
          // Picking the current sibling means "back to this level".
          // onGoTo no-ops when this is already the last entry.
          onClick={() => { setOpenKey(null); if (item.current) onGoTo(seg.index); else item.onSelect(); }}
        >
          <span className="nav-breadcrumb__menu-dot" aria-hidden="true" />
          {item.label}
        </button>
      ))}
    </div>
  );
}

/** Current level: there is no "back" target, so a plain click keeps
 * opening the jump menu. */
function CurrentSegmentMenu({ seg, sep, crumbClass, open, menu, toggleMenu }) {
  return (
    <>
      {sep}
      <li className={crumbClass}>
        <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={toggleMenu}>
          {seg.label}
          <span className="nav-breadcrumb__caret" aria-hidden="true">▾</span>
        </button>
        {menu}
      </li>
    </>
  );
}

/** Earlier level: click walks back like an address bar; the sibling menu
 * opens from the caret button, a right-click, or a press-and-hold. */
function EarlierSegmentMenu({ seg, sep, crumbClass, open, menu, toggleMenu, menuKey, goTo, consumeHold, startHold, cancelHold, setOpenKey }) {
  return (
    <>
      {sep}
      <li className={crumbClass}>
        <button
          type="button"
          onClick={() => { if (consumeHold()) return; goTo(seg); }}
          onContextMenu={(e) => { e.preventDefault(); setOpenKey(menuKey); }}
          onPointerDown={() => startHold(menuKey)}
          onPointerUp={cancelHold}
          onPointerLeave={cancelHold}
          onPointerCancel={cancelHold}
        >
          {seg.label}
        </button>
        <button
          type="button"
          className="nav-breadcrumb__caret-btn"
          aria-label={`Switch ${seg.label}`}
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={toggleMenu}
        >
          <span className="nav-breadcrumb__caret" aria-hidden="true">▾</span>
        </button>
        {menu}
      </li>
    </>
  );
}

/**
 * A breadcrumb segment whose siblings are known (`siblingsFor` returned
 * 2+): either the current segment (menu-only, no back target) or an
 * earlier one (click walks back, the caret/right-click/hold opens siblings).
 */
export default function NavBreadcrumbSegmentMenu({
  seg, sep, isLast, siblings, crumbClass, open, menuKey, setOpenKey, onGoTo, goTo, consumeHold, startHold, cancelHold,
}) {
  const toggleMenu = () => setOpenKey(open ? null : menuKey);
  const menu = open && <SiblingMenu siblings={siblings} seg={seg} onGoTo={onGoTo} setOpenKey={setOpenKey} />;

  if (isLast) {
    return <CurrentSegmentMenu seg={seg} sep={sep} crumbClass={crumbClass} open={open} menu={menu} toggleMenu={toggleMenu} />;
  }
  return (
    <EarlierSegmentMenu
      seg={seg} sep={sep} crumbClass={crumbClass} open={open} menu={menu} toggleMenu={toggleMenu}
      menuKey={menuKey} goTo={goTo} consumeHold={consumeHold} startHold={startHold} cancelHold={cancelHold} setOpenKey={setOpenKey}
    />
  );
}
