import { useMemo } from 'react';
import { t } from '../../../strings/index.js';

const TYPE_CONFIG = {
  wcag:      { labelKey: 'evaluate.stdWcag',      className: 'dimension-chip-type--wcag',      order: 1 },
  quodeq:    { labelKey: 'evaluate.stdQuodeq',    className: 'dimension-chip-type--quodeq',    order: 2 },
  custom:    { labelKey: 'evaluate.stdCustom',    className: 'dimension-chip-type--custom',    order: 4 },
  community: { labelKey: 'evaluate.stdCommunity', className: 'dimension-chip-type--community', order: 3 },
};
const DEFAULT_TYPE_CONFIG = { labelKey: 'evaluate.stdIso', className: 'dimension-chip-type--iso', order: 0 };

// This component's own terminal-styled picker variant (ReEvaluateCard); the
// default (no variant passed) is the chip grid. Not a shared UI concept.
export const DIMENSION_SELECTOR_VARIANT_TERMINAL = 'terminal';

function typeConfig(dim) { return TYPE_CONFIG[dim.standardType] || DEFAULT_TYPE_CONFIG; }

function typeInfo(dim) {
  const { labelKey, className, order } = typeConfig(dim);
  return { label: t(labelKey), className, order };
}

// The name a dimension is shown and sorted by: its label, else its id.
function dimensionName(dim) {
  return dim.label || dim.id;
}

// The dimension's ISO 25010 mapping when it has one, its own name otherwise.
function dimensionTitle(dim) {
  return dim.iso_25010 ? t('evaluate.iso25010Title', { value: dim.iso_25010 }) : dimensionName(dim);
}

// Both the compact chip and the full card are one toggle button for one
// dimension; only what they draw inside differs.
function DimensionToggle({ dim, isSelected, onToggle, className, children }) {
  return (
    <button
      type="button"
      className={className}
      title={dimensionTitle(dim)}
      aria-pressed={isSelected}
      onClick={() => onToggle(dim.id)}
    >
      {children}
    </button>
  );
}

function DimensionChip({ dim, isSelected, onToggle }) {
  const info = typeInfo(dim);
  return (
    <DimensionToggle
      dim={dim}
      isSelected={isSelected}
      onToggle={onToggle}
      className={`dimension-chip-btn${isSelected ? ' selected' : ''}`}
    >
      {dimensionName(dim)}
      <span className={`dimension-chip-type ${info.className}`}>{info.label}</span>
    </DimensionToggle>
  );
}

function DimensionCard({ dim, isSelected, onToggle, meta, metaLoading, upToDate }) {
  const info = typeInfo(dim);
  return (
    <DimensionToggle
      dim={dim}
      isSelected={isSelected}
      onToggle={onToggle}
      className={`eval-dim-card${isSelected ? ' eval-dim-card--selected' : ''}${upToDate ? ' eval-dim-card--uptodate' : ''}`}
    >
      <span className="eval-dim-card__check" aria-hidden="true">{isSelected ? '✓' : ''}</span>
      <span className="eval-dim-card__body">
        <span className="eval-dim-card__title-row">
          <span className="eval-dim-card__name">{dimensionName(dim)}</span>
          {/* Plain bordered tag on purpose: the legacy dimension-chip-type--*
              classes paint a tinted pill that fights the card style and
              drops contrast on several themes. */}
          <span className="eval-dim-card__std">{info.label.toLowerCase()}</span>
        </span>
        {meta != null ? (
          <span className="eval-dim-card__meta">
            {meta.map((line) => (
              <span key={line} className="eval-dim-card__meta-line">{line}</span>
            ))}
          </span>
        ) : metaLoading ? (
          // Estimates take a few seconds; a quiet placeholder keeps the card
          // from growing when the real meta lands.
          <span className="eval-dim-card__meta eval-dim-card__meta--skeleton" title={t('evaluate.estimating')} aria-hidden="true" />
        ) : null}
      </span>
    </DimensionToggle>
  );
}

function DimensionSelectorTerminal({ sorted, selectedDims, onToggle, onSelectAll, onClearAll, dimMetas, upToDateIds, metasLoading, seededFromLastRun }) {
  return (
    <div className="form-group eval-dims-section">
      <div className="dimension-label-row dimension-label-row--terminal">
        <span className="eval-dims-heading">
          <label>{t('evaluate.dimensionsLabel')}</label>
          <span className="eval-dims-counter">
            {t(seededFromLastRun ? 'evaluate.dimsSelectedCounterLastRun' : 'evaluate.dimsSelectedCounter', { selected: selectedDims.size, total: sorted.length })}
          </span>
        </span>
        <div className="dimension-chip-actions">
          <button type="button" className="dim-action-btn dim-action-btn--terminal" onClick={onSelectAll}>{t('evaluate.allBtn')}</button>
          <button type="button" className="dim-action-btn dim-action-btn--terminal" onClick={onClearAll}>{t('evaluate.clearBtn')}</button>
        </div>
      </div>

      <div className="eval-dim-grid">
        {sorted.map((dim) => (
          <DimensionCard
            key={dim.id}
            dim={dim}
            isSelected={selectedDims.has(dim.id)}
            onToggle={onToggle}
            meta={dimMetas?.[dim.id] ?? null}
            metaLoading={metasLoading}
            upToDate={upToDateIds?.has(dim.id) ?? false}
          />
        ))}
      </div>
    </div>
  );
}

function DimensionSelectorChips({ sorted, selectedDims, onToggle, onSelectAll, onClearAll }) {
  return (
    <div className="form-group">
      <div className="dimension-label-row">
        <label>{t('evaluate.dimensionsLabelCap')}</label>
        <div className="dimension-chip-actions">
          <button type="button" className="dim-action-btn" onClick={onSelectAll}>{t('evaluate.allCap')}</button>
          <button type="button" className="dim-action-btn" onClick={onClearAll}>{t('evaluate.clearCap')}</button>
        </div>
      </div>

      <div className="dimension-grid">
        {sorted.map((dim) => (
          <DimensionChip key={dim.id} dim={dim} isSelected={selectedDims.has(dim.id)} onToggle={onToggle} />
        ))}
      </div>
    </div>
  );
}

/**
 * @param {object} props
 * @param {object} [props.dimMetas] terminal variant only: dim id → pre-run
 *   meta lines (["312 files to analyze", "85% analyzed"]); null/missing → omitted.
 * @param {Set<string>} [props.upToDateIds] terminal variant only: ids of dimensions
 *   with nothing to analyze; their cards are muted.
 * @param {boolean} [props.seededFromLastRun] terminal variant only: the selection is
 *   still the one the project's last run used; the counter says so.
 * @param {boolean} [props.metasLoading] terminal variant only: estimates are
 *   still being computed — cards show a small placeholder instead of nothing.
 */
export default function DimensionSelector({ allDimensions, selectedDims, onToggle, onSelectAll, onClearAll, variant, dimMetas = null, upToDateIds = null, metasLoading = false, seededFromLastRun = false }) {
  const sorted = useMemo(() => [...allDimensions].sort((a, b) => {
    const oa = typeConfig(a).order;
    const ob = typeConfig(b).order;
    if (oa !== ob) return oa - ob;
    return dimensionName(a).localeCompare(dimensionName(b));
  }), [allDimensions]);

  const shared = { sorted, selectedDims, onToggle, onSelectAll, onClearAll };

  return variant === DIMENSION_SELECTOR_VARIANT_TERMINAL
    ? <DimensionSelectorTerminal {...shared} dimMetas={dimMetas} upToDateIds={upToDateIds} metasLoading={metasLoading} seededFromLastRun={seededFromLastRun} />
    : <DimensionSelectorChips {...shared} />;
}
