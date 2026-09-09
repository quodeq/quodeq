import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';

/**
 * Shared side-pane "log console" window: an open flag, a source hook that
 * streams/polls while open, and a buildSpec(source) that turns the source's
 * fields into a window spec. Used by OllamaLogProvider and ServerLogProvider,
 * which differ only in windowId, useLogSource and buildSpec.
 *
 * The `useLogSource` param name (not e.g. `logSourceHook`) keeps the
 * react-hooks lint heuristic — which flags hook calls by name — happy about
 * calling it here unconditionally.
 */
export function useLogWindow({ windowId, useLogSource, buildSpec }) {
  const [open, setOpen] = useState(false);
  const source = useLogSource(open);
  const { addWindow, removeWindow, replaceWindow, hasWindow } = useSidePane();

  const sourceValues = Object.values(source);
  const spec = useMemo(
    () => (open ? buildSpec(source) : null),
    // Deps are the source object's own field values (e.g. logs/status), not
    // `source` itself, so this only recomputes when a field actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [open, buildSpec, ...sourceValues],
  );

  useEffect(() => {
    if (spec) replaceWindow(spec);
  }, [spec, replaceWindow]);

  const openLog = useCallback(() => {
    setOpen(true);
    const fresh = buildSpec(source);
    addWindow(fresh);
    replaceWindow(fresh);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addWindow, replaceWindow, buildSpec, ...sourceValues]);

  const closeLog = useCallback(() => {
    setOpen(false);
    removeWindow(windowId);
  }, [removeWindow, windowId]);

  // Sync open state if the user closes the window via the X.
  useEffect(() => {
    if (open && !hasWindow(windowId)) setOpen(false);
  }, [open, hasWindow, windowId]);

  return useMemo(
    () => ({ open, openLog, closeLog }),
    [open, openLog, closeLog],
  );
}
