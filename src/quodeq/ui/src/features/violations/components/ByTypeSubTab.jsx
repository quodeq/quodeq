/** The By type sub-tab: the data hooks around ByTypeView. */
import ByTypeView from './ByTypeView.jsx';
import { useByTypeData } from '../hooks/useByTypeData.js';
import { useDismissByType } from '../hooks/useDismissByType.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

export default function ByTypeSubTab({ dimensions, project, selectedSource, callbacks }) {
  const { diffsByRun, standardsByDim, loading } = useByTypeData({ project, dimensions, selectedSource });
  const { dismissType, error, notice } = useDismissByType({
    project, selectedSource, onReconcile: callbacks.onReconcile, bumpDismissRefresh: callbacks.onBumpDismissRefresh,
  });
  const canDismiss = selectedSource !== PROJECT_SOURCE.SHARED;
  return (
    <>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {notice && <div className="info-banner" role="status">{notice}</div>}
      <ByTypeView
        dimensions={dimensions} diffsByRun={diffsByRun} standardsByDim={standardsByDim} loading={loading}
        onTypeClick={callbacks.onTypeClick} onDismissType={canDismiss ? dismissType : undefined}
      />
    </>
  );
}
