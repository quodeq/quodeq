import { useState, useRef } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';

const MAX_FILE_SIZE = 1024 * 1024; // 1MB
// File extension is product identity, not translatable prose.
const QUODEQ_FILE_EXT = '.quodeq';
const WARNINGS_MAX_HEIGHT = 200;
const CONFLICT_MAX_HEIGHT = 120;
const STEP = { PICK: 'pick', REVIEWING: 'reviewing', ERROR: 'error', WARNINGS: 'warnings', CONFLICT: 'conflict' };

function buildImportedCopyId(id) {
  return `${id}-imported`;
}

function PickStep({ fileRef, onFile, onClose }) {
  return (
    <>
      <h3 id="import-modal-title" className="modal-title">{t('standards.importEvaluatorTitle')}</h3>
      <p className="modal-body">{t('standards.selectFilePrefix')} <strong>{QUODEQ_FILE_EXT}</strong> {t('standards.selectFileSuffix')}</p>
      <input ref={fileRef} type="file" accept=".quodeq,.json" onChange={onFile} style={{ margin: '12px 0' }} />
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
      </div>
    </>
  );
}

function ImportingStep() {
  return (
    <>
      <h3 id="import-modal-title" className="modal-title">{t('standards.importingTitle')}</h3>
      <p className="modal-body">{t('standards.importingBody')}</p>
    </>
  );
}

function ErrorStep({ error, onClose }) {
  return (
    <>
      <h3 id="import-modal-title" className="modal-title">{t('standards.importFailedTitle')}</h3>
      <p className="modal-body modal-body--warning">{error}</p>
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={onClose}>{t('common.close')}</button>
      </div>
    </>
  );
}

function WarningsStep({ warnings, onClose, onProceed }) {
  return (
    <>
      <h3 id="import-modal-title" className="modal-title">{t('standards.securityWarningsTitle')}</h3>
      <p className="modal-body modal-body--warning">
        {t('standards.securityWarningsBody')}
      </p>
      <ul className="modal-body" style={{ fontSize: '0.85rem', maxHeight: WARNINGS_MAX_HEIGHT, overflow: 'auto' }}>
        {warnings.map((w, i) => <li key={i}>{w}</li>)}
      </ul>
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
        <button type="button" className="btn-primary" onClick={onProceed}>{t('standards.importAnyway')}</button>
      </div>
    </>
  );
}

function ConflictStep({ parsedData, conflict, warnings, actions }) {
  const { onClose, onImportAsCopy, onOverwrite } = actions;
  return (
    <>
      <h3 id="import-modal-title" className="modal-title">{t('standards.idExistsTitle')}</h3>
      <p className="modal-body">
        {t('standards.idExistsPrefix')} <strong>{parsedData?.id}</strong> {t('standards.idExistsSuffix')}
        {conflict?.name ? ` ("${conflict.name}")` : ''}.
      </p>
      {warnings.length > 0 && (
        <>
          <p className="modal-body modal-body--warning" style={{ fontSize: '0.85rem' }}>
            {t('standards.securityWarningsAlso')}
          </p>
          <ul className="modal-body" style={{ fontSize: '0.8rem', maxHeight: CONFLICT_MAX_HEIGHT, overflow: 'auto' }}>
            {warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </>
      )}
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
        <button type="button" className="btn-secondary" onClick={onImportAsCopy}>{t('standards.importAsCopy')}</button>
        <button type="button" className="btn-danger" onClick={onOverwrite}>{t('standards.overwrite')}</button>
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
    setError(err.message || t('standards.importFailed'));
    setStep(STEP.ERROR);
  }
}

async function handleFileInput(e, onImported, state, importStandard) {
  const { setStep, setError, setParsedData } = state;
  const file = e.target.files?.[0];
  if (!file) return;
  if (file.size > MAX_FILE_SIZE) {
    setError(t('standards.fileTooLarge', { size: (file.size / 1024).toFixed(0) }));
    setStep(STEP.ERROR);
    return;
  }
  let data;
  try {
    const text = await file.text();
    data = JSON.parse(text);
  } catch {
    setError(t('standards.invalidJson'));
    setStep(STEP.ERROR);
    return;
  }
  if (typeof data !== 'object' || Array.isArray(data)) {
    setError(t('standards.invalidJsonObject'));
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
      <div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="import-modal-title" onClick={(e) => e.stopPropagation()}>
        {step === STEP.PICK && <PickStep fileRef={fileRef} onFile={handleFile} onClose={onClose} />}
        {step === STEP.REVIEWING && <ImportingStep />}
        {step === STEP.ERROR && <ErrorStep error={error} onClose={onClose} />}
        {step === STEP.WARNINGS && <WarningsStep warnings={warnings} onClose={onClose} onProceed={handleProceedWithWarnings} />}
        {step === STEP.CONFLICT && <ConflictStep parsedData={parsedData} conflict={conflict} warnings={warnings} actions={{ onClose, onImportAsCopy: handleImportAsCopy, onOverwrite: handleForceImport }} />}
      </div>
    </div>
  );
}
