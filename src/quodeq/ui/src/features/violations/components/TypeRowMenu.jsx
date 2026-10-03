/** The per-type row menu: dismiss every finding of the type in a scope. */
import { useRef, useState } from 'react';
import { useBreadcrumbDismiss } from '../../explorer/components/useBreadcrumbDismiss.js';
import { t } from '../../../strings/index.js';
import { pluralKey } from '../../../utils/plural.js';
import { DISMISS_SCOPE } from '../violationsVocab.js';
import { principleCount } from '../hooks/useDismissByType.js';

export default function TypeRowMenu({ row, onDismissType }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  useBreadcrumbDismiss(open ? row.key : null, () => setOpen(false), rootRef);
  const count = row.now;
  const inPrinciple = principleCount(row);
  const pick = (scope) => { setOpen(false); onDismissType(row, scope); };
  return (
    <span className="type-row-menu" ref={rootRef}>
      <button
        type="button" className="type-row-menu__btn" aria-haspopup="menu" aria-expanded={open}
        aria-label={t('violations.typeMenuAria', { req: row.req })} onClick={() => setOpen((v) => !v)}
      >
        {t('violations.typeMenuGlyph')}
      </button>
      {open && (
        <div role="menu" className="type-row-menu__list">
          <button type="button" role="menuitem" onClick={() => pick(DISMISS_SCOPE.PROJECT)}>
            {t(pluralKey(count, 'violations.dismissAllProjectOne', 'violations.dismissAllProject'), { count })}
          </button>
          {row.principle && (
            <button type="button" role="menuitem" onClick={() => pick(DISMISS_SCOPE.PRINCIPLE)}>
              {t(pluralKey(inPrinciple, 'violations.dismissAllPrincipleOne', 'violations.dismissAllPrinciple'), { count: inPrinciple, principle: row.principle })}
            </button>
          )}
        </div>
      )}
    </span>
  );
}
