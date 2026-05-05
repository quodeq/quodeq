import { useEffect, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

/**
 * Fetch a standard's description plus a map of principle name -> description.
 * Dimensions in eval data correspond 1:1 with standard ids (reliability,
 * security, etc.), so the dimension is passed through to `getStandard`.
 *
 * Returns `{ standardDescription, principleDescriptions }`. Both fields are
 * empty until the fetch resolves; callers should treat undefined as "no
 * description" so the help icon stays hidden.
 */
export function useStandardDescriptions(dimension) {
  const { getStandard } = useApi();
  const [state, setState] = useState({ standardDescription: '', principleDescriptions: {} });

  useEffect(() => {
    if (!dimension) return;
    let cancelled = false;
    getStandard(dimension)
      .then((std) => {
        if (cancelled || !std) return;
        const principleDescriptions = {};
        for (const p of std.principles || []) {
          if (p?.name && p?.description) principleDescriptions[p.name] = p.description;
        }
        setState({
          standardDescription: std.description || '',
          principleDescriptions,
        });
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [dimension, getStandard]);

  return state;
}
