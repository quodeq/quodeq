import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { REPO_SOURCE } from '../onboardingVocab.js';
import { makeTryResumeExisting } from './resumeExisting.js';
import { startFolder, startUrl } from './analyzeLaunchStart.js';

/**
 * The add panel's `add`. A folder registers synchronously and is handed over
 * at once. A url is probed (unreachable opens the access panel), then posted
 * as a clone job (202) and handed over as "cloning": the panel closes and the
 * Repositories tab's tile shows the clone; when it lands the app selects the
 * project. A 409 PROJECT_EXISTS resumes the registered project and hands it
 * over. Closing the panel (unmount) drops any hand-over still in flight.
 *
 * `onAdded({ projectId, cloning })` is the hand-over; never after the panel
 * unmounted.
 *
 * @param {{ wizard: object, form: { request: () => object }, onAdded: Function }} args
 */
export function useAnalyzeLaunch({ wizard, form, onAdded }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const [accessFailure, setAccessFailure] = useState(null);
  const [startError, setStartError] = useState(null);
  const [starting, setStarting] = useState(false);
  const startingRef = useRef(false);
  const latest = useRef(null);
  // Closing the panel unmounts it: a registration or resume that resolves
  // after that must not hand anything over.
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const added = (outcome) => {
    if (mounted.current) latest.current.onAdded(outcome);
  };

  async function run() {
    if (startingRef.current) return;
    const request = form.request();
    startingRef.current = true;
    setStarting(true);
    setAccessFailure(null);
    setStartError(null);
    const ctx = { api, queryClient, wizard, set: { setAccessFailure, setStartError }, tryResume: latest.current.tryResume, added };
    try {
      await (request.source === REPO_SOURCE.FOLDER ? startFolder(ctx, request) : startUrl(ctx, request));
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
  }

  const tryResume = makeTryResumeExisting({ getProjectInfo: api.getProjectInfo, getProjectScan: api.getProjectScan, actions: wizard });
  latest.current = { onAdded, tryResume };

  return {
    run,
    busy: starting,
    accessFailure,
    startError: startError ? { ...startError, retry: run } : null,
  };
}
