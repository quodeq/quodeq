import { useState, useRef } from 'react';
import { importStandard } from '../../../api/index.js';

const MAX_FILE_SIZE = 1024 * 1024; // 1MB
const STEP = { PICK: 'pick', IMPORTING: 'importing', ERROR: 'error', WARNINGS: 'warnings', CONFLICT: 'conflict' };

export default function ImportModal({ onClose, onImported }) {
  const [step, setStep] = useState(STEP.PICK); // pick | warnings | conflict | importing | error
  const [error, setError] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [conflict, setConflict] = useState(null);
  const [parsedData, setParsedData] = useState(null);
  const fileRef = useRef(null);

  const handleFile = async (e) => {
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
    await doImport(data, false);
  };

  const doImport = async (data, force) => {
    setStep(STEP.IMPORTING);
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
  };

  const handleForceImport = async () => {
    await doImport(parsedData, true);
  };

  const handleImportAsCopy = async () => {
    const newId = `${parsedData.id}-imported`;
    const copied = { ...parsedData, id: newId };
    setParsedData(copied);
    await doImport(copied, false);
  };

  const handleProceedWithWarnings = async () => {
    await doImport(parsedData, true);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        {step === STEP.PICK && (
          <>
            <h3 className="modal-title">Import Evaluator</h3>
            <p className="modal-body">
              Select a <strong>.quodeq</strong> file to import.
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".quodeq,.json"
              onChange={handleFile}
              style={{ margin: '12px 0' }}
            />
            <div className="modal-actions">
              <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}

        {step === STEP.IMPORTING && (
          <>
            <h3 className="modal-title">Importing...</h3>
            <p className="modal-body">Validating and importing evaluator.</p>
          </>
        )}

        {step === STEP.ERROR && (
          <>
            <h3 className="modal-title">Import Failed</h3>
            <p className="modal-body modal-body--warning">{error}</p>
            <div className="modal-actions">
              <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
            </div>
          </>
        )}

        {step === STEP.WARNINGS && (
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
              <button type="button" className="btn-primary" onClick={handleProceedWithWarnings}>Import Anyway</button>
            </div>
          </>
        )}

        {step === STEP.CONFLICT && (
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
              <button type="button" className="btn-secondary" onClick={handleImportAsCopy}>Import as Copy</button>
              <button type="button" className="btn-danger" onClick={handleForceImport}>Overwrite</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
