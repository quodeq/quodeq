import { useState } from 'react';
import { exportStandard } from '../../../api/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

async function downloadStandard(standardId) {
  const { data, fileName } = await exportStandard(standardId);
  const content = JSON.stringify(data, null, 2);
  if (window.pywebview?.api?.save_file) {
    window.pywebview.api.save_file(content, fileName);
    return;
  }
  const blob = new Blob([content], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * StandardsTable.jsx's per-row modal state (delete/duplicate confirm,
 * download error) and the handlers that open/close/confirm them. Extracted
 * verbatim.
 */
export function useStandardRowModals({ standard, onDelete, onDuplicate }) {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const [downloadError, setDownloadError] = useState(null);

  const openDelete = () => setShowDeleteModal(true);
  const closeDelete = () => setShowDeleteModal(false);
  const confirmDelete = () => { setShowDeleteModal(false); onDelete(standard.id); };

  const openDuplicate = () => setShowDuplicateModal(true);
  const closeDuplicate = () => setShowDuplicateModal(false);
  const confirmDuplicate = (newId) => { setShowDuplicateModal(false); onDuplicate(standard.id, newId); };

  const handleDownload = () => {
    setDownloadError(null);
    downloadStandard(standard.id).catch((err) => {
      setDownloadError(apiErrorMessage(err, 'standards.downloadFailed'));
    });
  };

  return {
    showDeleteModal, showDuplicateModal, downloadError,
    openDelete, closeDelete, confirmDelete,
    openDuplicate, closeDuplicate, confirmDuplicate,
    handleDownload,
  };
}
