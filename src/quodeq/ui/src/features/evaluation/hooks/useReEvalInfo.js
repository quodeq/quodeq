/**
 * useReEvalInfo — loads/reloads a project's info for ReEvaluateCard, plus
 * the "restore a missing local path from its remote URL" flow.
 *
 * Split out of ReEvaluateCard.jsx verbatim.
 */
import { useState, useEffect } from 'react';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

export function useReEvalInfo(project, initialInfo, { getProjectInfo, relocateProject }) {
  const [info, setInfo] = useState(initialInfo || null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [urlInput, setUrlInput] = useState('');
  const [urlError, setUrlError] = useState(null);
  const [urlSaving, setUrlSaving] = useState(false);

  useEffect(() => {
    if (!project) return;
    // Always fetch full info (listing doesn't include hasFingerprints)
    getProjectInfo(project)
      .then((result) => {
        setInfo(result);
        setError(null);
      })
      .catch(() => {
        if (!initialInfo) {
          setInfo(null);
          setError(t('evaluate.projectInfoLoadFailed'));
        }
      });
  }, [project, reloadKey]);

  const retry = () => setReloadKey((k) => k + 1);

  async function handleUrlRestore() {
    const url = urlInput.trim();
    if (!url) return;
    setUrlSaving(true);
    setUrlError(null);
    try {
      await relocateProject(project, url);
      const updated = await getProjectInfo(project);
      setInfo(updated);
      setUrlInput('');
    } catch (err) {
      setUrlError(apiErrorMessage(err, 'evaluate.urlUpdateFailed'));
    } finally {
      setUrlSaving(false);
    }
  }

  return { info, error, retry, urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore };
}
