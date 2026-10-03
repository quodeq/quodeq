import { useState, useRef } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { classifyImportResult, parseImportFile, IMPORT_OUTCOME, PARSE_FILE_ERROR, BYTES_PER_KB } from '../utils/importResult.js';

export const STEP = { PICK: 'pick', REVIEWING: 'reviewing', ERROR: 'error', WARNINGS: 'warnings', CONFLICT: 'conflict' };

function buildImportedCopyId(id) {
  return `${id}-imported`;
}

async function importEvaluator(data, force, onImported, state, importStandard) {
  const { setStep, setError, setWarnings, setConflict } = state;
  setStep(STEP.REVIEWING);
  try {
    const result = await importStandard(data, force);
    const outcome = classifyImportResult(result, force);
    if (outcome.kind === IMPORT_OUTCOME.CONFLICT) {
      setConflict(outcome.conflict);
      setWarnings(outcome.warnings);
      setStep(STEP.CONFLICT);
      return;
    }
    if (outcome.kind === IMPORT_OUTCOME.WARNINGS) {
      setWarnings(outcome.warnings);
      setStep(STEP.WARNINGS);
      return;
    }
    onImported(outcome.id ?? data?.id);
  } catch (err) {
    setError(apiErrorMessage(err, 'standards.importFailed'));
    setStep(STEP.ERROR);
  }
}

async function handleFileInput(e, onImported, state, importStandard) {
  const { setStep, setError, setParsedData } = state;
  const file = e.target.files?.[0];
  if (!file) return;
  const parsed = await parseImportFile(file);
  if (!parsed.ok) {
    if (parsed.error === PARSE_FILE_ERROR.TOO_LARGE) {
      setError(t('standards.fileTooLarge', { size: (parsed.size / BYTES_PER_KB).toFixed(0) }));
    } else if (parsed.error === PARSE_FILE_ERROR.INVALID_JSON) {
      console.warn('[ImportModal] could not parse imported file:', parsed.cause);
      setError(t('standards.invalidJson'));
    } else {
      setError(t('standards.invalidJsonObject'));
    }
    setStep(STEP.ERROR);
    return;
  }
  setParsedData(parsed.data);
  await importEvaluator(parsed.data, false, onImported, state, importStandard);
}

function useImportActions(onImported, state, importStandard) {
  const { parsedData, setParsedData } = state;

  const handleFile = async (e) => handleFileInput(e, onImported, state, importStandard);
  // One action, offered from two steps: "overwrite the conflicting standard"
  // on the conflict step and "import anyway" on the warnings step.
  const handleImportAnyway = async () => {
    await importEvaluator(parsedData, true, onImported, state, importStandard);
  };
  const handleImportAsCopy = async () => {
    const copied = { ...parsedData, id: buildImportedCopyId(parsedData.id) };
    setParsedData(copied);
    await importEvaluator(copied, false, onImported, state, importStandard);
  };
  return { handleFile, handleImportAnyway, handleImportAsCopy };
}

/**
 * ImportModal's flow: file pick -> parse -> importStandard, through the
 * conflict/warnings/error steps. `classifyImportResult` and
 * `parseImportFile` (utils/importResult.js) hold the pure branching logic;
 * this hook wires it to view state and the API client.
 */
export function useImportFlow(onImported) {
  const { importStandard } = useApi();
  const [step, setStep] = useState(STEP.PICK);
  const [error, setError] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [conflict, setConflict] = useState(null);
  const [parsedData, setParsedData] = useState(null);
  const fileRef = useRef(null);
  const actions = useImportActions(onImported, { setStep, setError, setWarnings, setConflict, parsedData, setParsedData }, importStandard);

  return { step, error, warnings, conflict, parsedData, fileRef, ...actions };
}
