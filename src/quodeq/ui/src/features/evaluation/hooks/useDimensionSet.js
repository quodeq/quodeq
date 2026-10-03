import { useState } from 'react';
import { t } from '../../../strings/index.js';

const NO_STANDARDS_MESSAGE = t('evaluate.noStandardsMessage');

/**
 * The set of dimensions picked for an evaluation, with the toggle, select-all
 * and clear actions the pickers bind to.
 *
 * `refuseEmptySelection` guards a start: with dimensions available but none
 * picked it reports through `onValidationFail` and returns true.
 * @param {Array<{id: string}>} allDimensions
 * @returns {{selectedDims: Set<string>, setSelectedDims: Function, toggleDim: (id: string) => void,
 *   selectAll: () => void, clearAll: () => void, refuseEmptySelection: (onValidationFail?: Function) => boolean}}
 */
export function useDimensionSet(allDimensions) {
  const [selectedDims, setSelectedDims] = useState(new Set());

  const toggleDim = (id) => setSelectedDims((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  const selectAll = () => setSelectedDims(new Set(allDimensions.map((d) => d.id)));
  const clearAll = () => setSelectedDims(new Set());
  const refuseEmptySelection = (onValidationFail) => {
    if (allDimensions.length > 0 && selectedDims.size === 0) {
      onValidationFail?.(NO_STANDARDS_MESSAGE);
      return true;
    }
    return false;
  };

  return { selectedDims, setSelectedDims, toggleDim, selectAll, clearAll, refuseEmptySelection };
}
