import { t } from '../../../strings/index.js';
import { useImportFlow, STEP } from '../hooks/useImportFlow.js';

// File extension is product identity, not translatable prose.
const QUODEQ_FILE_EXT = '.quodeq';
const WARNINGS_MAX_HEIGHT = 200;
const CONFLICT_MAX_HEIGHT = 120;

function PickStep({ fileRef, onFile, onClose }) {
  return (
    <>
      <h3 id="import-modal-title" className="modal-title">{t('standards.importEvaluatorTitle')}</h3>
      <p className="modal-body">{t('standards.selectFilePrefix')} <strong>{QUODEQ_FILE_EXT}</strong> {t('standards.selectFileSuffix')}</p>
      <input
        ref={fileRef}
        type="file"
        accept=".quodeq,.json"
        onChange={onFile}
        style={{ margin: '12px 0' }}
        aria-label={t('standards.importFileAria')}
      />
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

export default function ImportModal({ onClose, onImported }) {
  const {
    step, error, warnings, conflict, parsedData,
    fileRef, handleFile, handleImportAnyway, handleImportAsCopy,
  } = useImportFlow(onImported);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="import-modal-title" onClick={(e) => e.stopPropagation()}>
        {step === STEP.PICK && <PickStep fileRef={fileRef} onFile={handleFile} onClose={onClose} />}
        {step === STEP.REVIEWING && <ImportingStep />}
        {step === STEP.ERROR && <ErrorStep error={error} onClose={onClose} />}
        {step === STEP.WARNINGS && <WarningsStep warnings={warnings} onClose={onClose} onProceed={handleImportAnyway} />}
        {step === STEP.CONFLICT && <ConflictStep parsedData={parsedData} conflict={conflict} warnings={warnings} actions={{ onClose, onImportAsCopy: handleImportAsCopy, onOverwrite: handleImportAnyway }} />}
      </div>
    </div>
  );
}
