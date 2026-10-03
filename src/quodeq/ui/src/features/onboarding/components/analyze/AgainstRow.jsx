import { t } from '../../../../strings/index.js';
import StandardList, { INPUT_TYPE } from './StandardList.jsx';

/**
 * The analyze screen's "Against" row: the picked standard's name and the
 * dimensions it covers, with `change` revealing the picker (one or several
 * standards, each click a toggle).
 *
 * @param {object} props
 * @param {{ ids: string[], name: string, dimensions: string[], pickerOpen: boolean,
 *   openPicker: Function, closePicker: Function, pick: (id: string) => void }} props.standard
 * @param {object[]} props.standards - the visible standards
 */
export default function AgainstRow({ standard, standards }) {
  return (
    <section className="analyze-row">
      <h3 className="analyze-row__title">{t('onboarding.against')}</h3>
      <div className="analyze-row__body">
        <span className="analyze-row__name">{standard.name}</span>
        {standard.dimensions.length > 0 && (
          <span className="analyze-row__meta">{standard.dimensions.join(', ')}</span>
        )}
        {!standard.pickerOpen && (
          <button type="button" className="onboarding-edit-link" aria-label={t('onboarding.changeStandard')} onClick={standard.openPicker}>
            {t('onboarding.change')}
          </button>
        )}
      </div>
      {standard.pickerOpen && (
        <div className="analyze-row__drawer">
          <StandardList
            standards={standards}
            inputType={INPUT_TYPE.CHECKBOX}
            isChecked={(id) => standard.ids.includes(id)}
            onToggle={standard.pick}
          />
          <button type="button" className="term-btn term-btn--secondary" onClick={standard.closePicker}>{t('onboarding.done')}</button>
        </div>
      )}
    </section>
  );
}
