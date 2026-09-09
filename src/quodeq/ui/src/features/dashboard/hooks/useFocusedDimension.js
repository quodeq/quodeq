import { useEffect, useRef, useState } from 'react';

// Clear focused dimension when the active run changes to avoid showing stale data
export function useFocusedDimension(selectedRunId) {
  const [focusedDimension, setFocusedDimension] = useState(null);
  const prevRunRef = useRef(selectedRunId);
  useEffect(() => {
    if (prevRunRef.current !== selectedRunId) {
      prevRunRef.current = selectedRunId;
      setFocusedDimension(null);
    }
  }, [selectedRunId]);
  return [focusedDimension, setFocusedDimension];
}
