import { useState, useRef } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

const MAX_FILE_SIZE = 1024 * 1024; // 1MB
const STEP = { PICK: 'pick', REVIEWING: 'reviewing', ERROR: 'error', WARNINGS: 'warnings', CONFLICT: 'conflict' };

function buildImportedCopyId(id) {
  return `${id}-imported`;
}

function PickStep({ fileRef, onFile, onClose }) {
  return (
    <>
      <h3 className="modal-title">Import Evaluator</h3>
      <p className="modal-body">Select a <strong>.quodeq</strong> file to import.</p>
      <input ref={fileRef} type="file" accept=".quodeq,.json" onChange={onFile} style={{ margin: '12px 0' }} />
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
      </div>
    </>
  );
}

function ImportingStep() {
  return (
    <>
      <h3 className="modal-title">Importing...</h3>
      <p className="modal-body">Validating and importing evaluator.</p>
    </>
  );
}

function ErrorStep({ error, onClose }) {
  return (
    <>
      <h3 className="modal-title">Import Failed</h3>
      <p className="modal-body modal-body--warning">{error}</p>
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
      </div>
    </>
  );
}

function WarningsStep({ warnings, onClose, onProceed }) {
  return (
    <>
      <h3 className="modal-title">Security Warnings</h3>
      <p className="modal-body modal-body--warning">
        This evaluator contains text that may attempt to manipulate the AI during analysis:
      </p>
      <ul className="modal-body" style={{ fontSize: '0.85rem', maxHeight: 200, overflow: 'auto' }}>
        {warnings.map((w, i) => <li key={i}>{w}</li>)}
      </ul>
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
        <button type="button" className="btn-primary" onClick={onProceed}>Import Anyway</button>
      </div>
    </>
  );
}

function ConflictStep({ parsedData, conflict, warnings, actions }) {
  const { onClose, onImportAsCopy, onOverwrite } = actions;
  return (
    <>
      <h3 className="modal-title">ID Already Exists</h3>
      <p className="modal-body">
        A standard with ID <strong>{parsedData?.id}</strong> already exists
        {conflict?.name ? ` ("${conflict.name}")` : ''}.
      </p>
      {warnings.length > 0 && (
        <>
          <p className="modal-body modal-body--warning" style={{ fontSize: '0.85rem' }}>
            Security warnings were also detected:
          </p>
          <ul className="modal-body" style={{ fontSize: '0.8rem', maxHeight: 120, overflow: 'auto' }}>
            {warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </>
      )}
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
        <button type="button" className="btn-secondary" onClick={onImportAsCopy}>Import as Copy</button>
        <button type="button" className="btn-danger" onClick={onOverwrite}>Overwrite</button>
      </div>
    </>
  );
}

async function importEvaluator(data, force, onImported, state, importStandard) {
  const { setStep, setError, setWarnings, setConflict } = state;
  setStep(STEP.REVIEWING);
  try {
    const result = await importStandard(data, force);
    if (result._conflict) {
      setConflict(result.existing);
      setWarnings(result.warnings || []);
      setStep(STEP.CONFLICT);
      return;
    }
    if (result.warnings?.length > 0 && !force) {
      setWarnings(result.warnings);
      setStep(STEP.WARNINGS);
      return;
    }
    onImported();
  } catch (err) {
    setError(err.message || 'Import failed');
    setStep(STEP.ERROR);
  }
}

async function handleFileInput(e, onImported, state, importStandard) {
  const { setStep, setError, setParsedData } = state;
  const file = e.target.files?.[0];
  if (!file) return;
  if (file.size > MAX_FILE_SIZE) {
    setError(`File too large (${(file.size / 1024).toFixed(0)} KB). Maximum is 1 MB.`);
    setStep(STEP.ERROR);
    return;
  }
  let data;
  try {
    const text = await file.text();
    data = JSON.parse(text);
  } catch {
    setError('Invalid file: could not parse as JSON.');
    setStep(STEP.ERROR);
    return;
  }
  if (typeof data !== 'object' || Array.isArray(data)) {
    setError('Invalid file: expected a JSON object.');
    setStep(STEP.ERROR);
    return;
  }
  setParsedData(data);
  await importEvaluator(data, false, onImported, state, importStandard);
}

function useImportActions(onImported, state, importStandard) {
  const { parsedData, setParsedData } = state;

  const handleFile = async (e) => handleFileInput(e, onImported, state, importStandard);
  const handleForceImport = async () => { await importEvaluator(parsedData, true, onImported, state, importStandard); };
  const handleImportAsCopy = async () => {
    const copied = { ...parsedData, id: buildImportedCopyId(parsedData.id) };
    setParsedData(copied);
    await importEvaluator(copied, false, onImported, state, importStandard);
  };
  const handleProceedWithWarnings = async () => { await importEvaluator(parsedData, true, onImported, state, importStandard); };
  return { handleFile, handleForceImport, handleImportAsCopy, handleProceedWithWarnings };
}

function useImportModal(onImported) {
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

export default function ImportModal({ onClose, onImported }) {
  const {
    step, error, warnings, conflict, parsedData,
    fileRef, handleFile, handleForceImport,
    handleImportAsCopy, handleProceedWithWarnings,
  } = useImportModal(onImported);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        {step === STEP.PICK && <PickStep fileRef={fileRef} onFile={handleFile} onClose={onClose} />}
        {step === STEP.REVIEWING && <ImportingStep />}
        {step === STEP.ERROR && <ErrorStep error={error} onClose={onClose} />}
        {step === STEP.WARNINGS && <WarningsStep warnings={warnings} onClose={onClose} onProceed={handleProceedWithWarnings} />}
        {step === STEP.CONFLICT && <ConflictStep parsedData={parsedData} conflict={conflict} warnings={warnings} actions={{ onClose, onImportAsCopy: handleImportAsCopy, onOverwrite: handleForceImport }} />}
      </div>
    </div>
  );
}
