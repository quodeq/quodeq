/**
 * One line per scoring stage with its value: the worked example beside the
 * grade-formula sliders. The row order is the scoring order.
 */
import { t } from '../../../strings/index.js';

const ONE_DECIMAL = 1;
const TWO_DECIMALS = 2;

function num(v, decimals = ONE_DECIMAL) {
  return typeof v === 'number' ? v.toFixed(decimals) : '-';
}

/**
 * @param {Object} stages the explain endpoint's stage block
 * @returns {Array<{key: string, label: string, value: string}>}
 */
export function stageRows(stages) {
  return [
    { key: 'rules', label: t('helpFigure.stageRules'),
      value: t('helpFigure.stageRulesValue', { rules: stages.violationRules, mass: num(stages.violationMass, TWO_DECIMALS) }) },
    { key: 'base', label: t('helpFigure.stageBase'), value: num(stages.base) },
    { key: 'lift', label: t('helpFigure.stageLift'),
      value: t('helpFigure.stageLiftValue', { rules: stages.complianceRules, lift: num(stages.lift, TWO_DECIMALS) }) },
    { key: 'raw', label: t('helpFigure.stageRaw'), value: num(stages.raw) },
    { key: 'ceiling', label: t('helpFigure.stageCeiling'), value: num(stages.ceiling) },
    { key: 'floor', label: t('helpFigure.stageFloor'), value: num(stages.floor) },
    { key: 'final', label: t('helpFigure.stageFinal'), value: t('helpFigure.stageFinalValue', { score: num(stages.final), grade: stages.grade }) },
  ];
}

/**
 * The rows and the final "score grade" of one principle of the explain
 * payload, or nulls when the scorer found it insufficient.
 * @param {{insufficient: boolean, stages: Object|null}} principle
 * @returns {{insufficient: boolean, rows: Array|null, final: string|null}}
 */
export function stageSummary(principle) {
  if (!principle || principle.insufficient || !principle.stages) {
    return { insufficient: true, rows: null, final: null };
  }
  const rows = stageRows(principle.stages);
  return { insufficient: false, rows, final: rows[rows.length - 1].value };
}
