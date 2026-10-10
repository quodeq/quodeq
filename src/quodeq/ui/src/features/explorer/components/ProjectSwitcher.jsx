import { useEffect, useId, useRef } from 'react';
import { GradeChip } from '../../dashboard/components/projectCards/ProjectCardParts.jsx';
import { useSwitcherListNav } from '../../../hooks/useSwitcherListNav.js';
import { isMacPlatform } from '../../../hooks/useProjectSwitcherHotkey.js';
import { KEY } from '../../../vocab/keyboard.js';
import { activateOnKey } from '../../../utils/a11y.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { t } from '../../../strings/index.js';

/** One project row. Mouse hover moves the keyboard highlight with it so
 * the two never disagree about which row Enter would pick. */
function SwitcherOption({ row, optionId, isActive, isCurrent, onPick, onHover }) {
  const cls = `project-switcher__option${isActive ? ' is-active' : ''}${isCurrent ? ' is-current' : ''}`;
  return (
    <li
      id={optionId}
      role="option"
      aria-selected={isActive}
      aria-current={isCurrent || undefined}
      className={cls}
      // mousedown, not click: keep focus in the search field.
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => onPick(row)}
      // Keys normally stay in the search field (aria-activedescendant); this
      // covers an option that got focus some other way.
      tabIndex={-1}
      onKeyDown={activateOnKey(() => onPick(row))}
      onMouseEnter={onHover}
    >
      <span className="project-switcher__name">{row.label}</span>
      {row.source === PROJECT_SOURCE.SHARED && <span className="project-switcher__remote">{t('explorer.switcherRemoteTag')}</span>}
      <GradeChip grade={row.grade} />
    </li>
  );
}

/** The popover: search, project list, footer actions. Mounted only while
 * open, so the query and highlight reset on every opening. */
function SwitcherPopover({ rows, currentId, onPick, onAllRepositories, onAddProject, onEscape }) {
  const listId = useId();
  const listRef = useRef(null);
  const { query, setQuery, visible, activeIndex, setActive, onKeyDown } = useSwitcherListNav(rows, currentId, onPick);
  const optionId = (i) => `${listId}-opt-${i}`;

  useEffect(() => {
    listRef.current?.querySelector('.is-active')?.scrollIntoView?.({ block: 'nearest' });
  }, [activeIndex, visible]);

  return (
    <div className="project-switcher" role="dialog" aria-label={t('explorer.switcherAria')}>
      <input
        type="text"
        className="project-switcher__search"
        role="combobox"
        aria-expanded="true"
        aria-controls={listId}
        aria-activedescendant={visible.length ? optionId(activeIndex) : undefined}
        aria-label={t('explorer.switcherSearchAria')}
        placeholder={t('explorer.switcherSearchPlaceholder')}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => { if (e.key === KEY.ESCAPE) onEscape(); else onKeyDown(e); }}
        // The popover opens to be typed into.
        autoFocus
        spellCheck={false}
        autoComplete="off"
      />
      <ul id={listId} ref={listRef} className="project-switcher__list" role="listbox" aria-label={t('explorer.switcherListAria')}>
        {visible.map((row, i) => (
          <SwitcherOption
            key={row.id} row={row} optionId={optionId(i)} isActive={i === activeIndex}
            isCurrent={row.id === currentId} onPick={onPick} onHover={() => setActive(i)}
          />
        ))}
      </ul>
      {visible.length === 0 && <p className="project-switcher__empty">{t('explorer.switcherEmpty')}</p>}
      <div className="project-switcher__footer">
        <button type="button" className="project-switcher__btn" onClick={onAllRepositories}>
          {t('explorer.switcherAllRepositories')}
        </button>
        <button type="button" className="project-switcher__btn project-switcher__btn--primary" onClick={onAddProject}>
          <span aria-hidden="true">+</span> {t('projects.addProject')}
        </button>
      </div>
    </div>
  );
}

/**
 * The breadcrumb's project root as a switcher: the crumb opens a popover
 * listing every local and remote project instead of navigating to Repositories.
 * Open state is the breadcrumb's own `openKey`, so it shares the other
 * crumb menus' outside-press and Escape dismissal and never stacks on them.
 */
export default function ProjectSwitcherCrumb({ seg, sep, crumbClass, open, setOpen, switcher }) {
  const triggerRef = useRef(null);
  const { rows, currentId, onPick, onAllRepositories, onAddProject } = switcher;
  const close = () => setOpen(false);
  const then = (fn) => (...args) => { close(); fn(...args); };
  const shortcut = isMacPlatform() ? '⌘P' : 'Ctrl+P';

  return (
    <>
      {sep}
      <li className={`${crumbClass} nav-breadcrumb__crumb--switcher`}>
        <button
          ref={triggerRef}
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          title={t('explorer.switcherTitle', { shortcut })}
          onClick={() => setOpen(!open)}
        >
          {seg.label}
          <span className="nav-breadcrumb__caret" aria-hidden="true">▾</span>
        </button>
        {open && (
          <SwitcherPopover
            rows={rows}
            currentId={currentId}
            // Picking the project already active just closes the switcher.
            onPick={then((row) => { if (row.id !== currentId) onPick(row); })}
            onAllRepositories={then(onAllRepositories)}
            onAddProject={then(onAddProject)}
            onEscape={() => { close(); triggerRef.current?.focus(); }}
          />
        )}
      </li>
    </>
  );
}
