export default function EmptyState({ title, description, actionLabel, onAction, icon }) {
  return (
    <section className="empty-state">
      {icon && <div className="empty-state__icon" aria-hidden="true">{icon}</div>}
      <h2>{title}</h2>
      {description && <p>{description}</p>}
      {actionLabel && onAction && (
        <button type="button" className="empty-state-btn" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </section>
  );
}
