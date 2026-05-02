/**
 * AddProjectModal — wraps the existing EvaluationForm in a modal overlay.
 *
 * Used from ProjectsPage so "Add project" is the entry point on the Projects
 * tab. After the form's onStart fires, the modal closes and the parent
 * navigates to the Evaluate tab where EvaluationStatus takes over.
 */
import { useEffect } from 'react';
import EvaluationForm from '../../evaluation/components/EvaluationForm.jsx';

export default function AddProjectModal({ open, onClose, onStart }) {
  useEffect(() => {
    if (!open) return undefined;
    function onKey(e) { if (e.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  function handleStart(payload) {
    onStart(payload);
    onClose();
  }

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div
        className="add-project-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-project-modal-title"
      >
        <div className="add-project-modal__header">
          <h2 id="add-project-modal-title" className="add-project-modal__title">Add project</h2>
          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Close add-project dialog"
          >
            &times;
          </button>
        </div>
        <div className="add-project-modal__body">
          <EvaluationForm onStart={handleStart} disabled={false} selectedProject={null} />
        </div>
      </div>
    </div>
  );
}
