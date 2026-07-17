import ContextBlock from '../../../components/ContextBlock.jsx';

function dismissedLabel(d) {
  return d.principle || d.dimension || (d.req ?? '?');
}

function DismissedCard({ d, onRestore, onDelete }) {
  return (
    <div className="dismissed-card">
      <div className="dismissed-card-top">
        <span className="dismissed-tag">dismissed</span>
        {d.severity && <span className={`severity-tag ${d.severity}`}>{d.severity}</span>}
        <span className="dismissed-label">[{dismissedLabel(d)}]</span>
        <span className="dismissed-file">{d.file}:{d.line}</span>
        {/* onRestore/onDelete arrive as `undefined` for shared projects (no
            mutation route exists on the backend) — hide the actions rather
            than render a button that would silently no-op on click. */}
        {onRestore && <button type="button" className="restore-btn" onClick={() => onRestore(d)}>Restore</button>}
        {onDelete && <button type="button" className="delete-btn" onClick={() => onDelete(d)}>Delete</button>}
      </div>
      {(d.reason || d.title) && (
        <div className="dismissed-detail">
          {d.title && (
            <div className="dismissed-detail-section">
              <div className="dismissed-detail-header">
                <span className="dismissed-detail-label">Reason</span>
                {(() => {
                  const urlRefs = (d.reqRefs || []).filter((r) => r.url && /^https?:\/\//.test(r.url));
                  return urlRefs.length > 0 && (
                    <span className="cwe-link-group">
                      {urlRefs.map((r, i) => (
                        <a key={i} className="cwe-link" href={r.url} target="_blank" rel="noopener noreferrer">{r.label}</a>
                      ))}
                    </span>
                  );
                })()}
              </div>
              <p className="dismissed-detail-title">{d.title}</p>
            </div>
          )}
          {d.reason && (
            <div className="dismissed-detail-section">
              <span className="dismissed-detail-label">Detail</span>
              <p className="dismissed-detail-text">{d.reason}</p>
            </div>
          )}
          <ContextBlock context={d.context} snippet={d.snippet} scope={d.scope} line={d.line} endLine={d.endLine} />
        </div>
      )}
    </div>
  );
}

export default function DismissedSubTab({ dismissed, onRestore, onRestoreAll, onDelete, onDeleteAll }) {
  if (dismissed.length === 0) {
    return <p className="empty-state">No dismissed findings.</p>;
  }
  return (
    <>
      <div className="section-header">
        <h3 className="section-title">Dismissed Findings</h3>
        <span className="section-count">{dismissed.length} findings · not included in scoring</span>
        {dismissed.length > 1 && (
          <>
            {onRestoreAll && (
              <button type="button" className="restore-btn" style={{ marginLeft: 'auto' }} onClick={onRestoreAll}>
                Restore all
              </button>
            )}
            {onDeleteAll && (
              <button type="button" className="delete-btn" onClick={onDeleteAll}>
                Delete all
              </button>
            )}
          </>
        )}
      </div>
      <div className="dismissed-list-inner">
        {dismissed.map((d) => (
          <DismissedCard
            key={`${d.req}-${d.file}-${d.line}`}
            d={d}
            onRestore={onRestore}
            onDelete={onDelete}
          />
        ))}
      </div>
    </>
  );
}
