/**
 * Confirm dialog shown before saving threshold overrides that change a
 * dimension's effective params. Changed dimensions' cached results become
 * unreachable until re-analysis (reverting restores them), so the user
 * confirms before the save is committed.
 */
export default function ThresholdImpactDialog({ changedDimensions, onCancel, onSave, onSaveAndRescan }) {
  const many = changedDimensions.length > 1;
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="threshold-impact-title" onClick={(e) => e.stopPropagation()}>
        <h3 id="threshold-impact-title" className="modal-title">Thresholds changed</h3>
        <p className="modal-body">
          This change rewrites the rules for <strong>{changedDimensions.join(', ')}</strong>.
          Analyzed files in {many ? 'these dimensions' : 'this dimension'} will need
          re-analysis and will show as pending until the next scan. Restoring the previous
          values brings the current results back without a re-scan.
        </p>
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button type="button" className="btn-secondary" onClick={onSave}>Save</button>
          {onSaveAndRescan && (
            <button type="button" className="btn-primary" onClick={onSaveAndRescan}>Save and re-scan now</button>
          )}
        </div>
      </div>
    </div>
  );
}
