import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { COPY_FEEDBACK_MS } from '../../../components/CopyButton.jsx';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';

const NO_INVITE = Object.freeze({ copied: false, fallbackText: null });

/**
 * The sync strip's "copy invite": fetches the invite text (GET
 * /shared/invite, so the copy matches the catalog the server owns) and puts
 * it on the clipboard with a short "copied" flash. The desktop webview can
 * lack a clipboard, so a write that does not land shows the text inline
 * instead (`fallbackText`) for the user to copy by hand. A failed fetch is
 * toasted.
 * @returns {{invite: {copied: boolean, fallbackText: string|null}, copyInvite: () => Promise<void>}}
 */
export function useCopyInvite() {
  const { getInvite } = useApi();
  const { showToast } = useSidePane();
  const [invite, setInvite] = useState(NO_INVITE);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  const copyInvite = useCallback(async () => {
    let text;
    try {
      ({ text } = await getInvite());
    } catch (err) {
      console.warn('[useCopyInvite] invite fetch failed:', err);
      showToast(apiErrorMessage(err, 'sync.inviteFailed'));
      return;
    }
    if (!(await copyToClipboard(text))) {
      setInvite({ copied: false, fallbackText: text });
      return;
    }
    setInvite({ copied: true, fallbackText: null });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setInvite(NO_INVITE), COPY_FEEDBACK_MS);
  }, [getInvite, showToast]);

  return { invite, copyInvite };
}
