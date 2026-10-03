import HelpHint from '../../../../components/HelpHint.jsx';

// The list's <input> type: a radio picks exactly one, a checkbox any number.
export const INPUT_TYPE = Object.freeze({ RADIO: 'radio', CHECKBOX: 'checkbox' });

function StandardListItem({ s, inputType, checked, onToggle }) {
  return (
    <li>
      <label className={checked ? 'onboarding-standard-card onboarding-standard-card--selected' : 'onboarding-standard-card'}>
        <input
          type={inputType}
          name={inputType === INPUT_TYPE.RADIO ? 'standard' : `standard-${s.id}`}
          checked={checked}
          onChange={() => onToggle(s.id)}
          aria-label={s.name}
        />
        <div className="onboarding-standard-card__body">
          <strong>{s.name}</strong>
          {s.description && (
            <span
              className="onboarding-standard-card__hint"
              onClick={(e) => e.preventDefault()}
            >
              <HelpHint label={`${s.name} description`}>{s.description}</HelpHint>
            </span>
          )}
        </div>
      </label>
    </li>
  );
}

/**
 * The standard picker's cards: one per standard, checked by `isChecked`,
 * each toggle reported with the standard's id. Shared by the analyze
 * screen's `change` and the resume flow's standard step.
 *
 * @param {object} props
 * @param {Array<{ id: string, name: string, description?: string }>} props.standards
 * @param {'radio'|'checkbox'} props.inputType
 * @param {(id: string) => boolean} props.isChecked
 * @param {(id: string) => void} props.onToggle
 */
export default function StandardList({ standards, inputType, isChecked, onToggle }) {
  return (
    <ul className="onboarding-standard-list">
      {standards.map((s) => (
        <StandardListItem key={s.id} s={s} inputType={inputType} checked={isChecked(s.id)} onToggle={onToggle} />
      ))}
    </ul>
  );
}
