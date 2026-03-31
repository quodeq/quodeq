import StandardCard from './StandardCard.jsx';

function SectionHeader({ title, count }) {
  return (
    <div className="standards-section-header">
      <h2 className="standards-section-title">{title}</h2>
      <span className="standards-section-count">{count}</span>
    </div>
  );
}

function StandardsSection({ title, standards, onEdit, onDelete, onDuplicate, isVisible, onToggleVisibility }) {
  if (standards.length === 0) return null;
  return (
    <section className="standards-section">
      <SectionHeader title={title} count={standards.length} />
      <div className="standards-grid">
        {standards.map((s) => (
          <StandardCard
            key={s.id}
            standard={s}
            onEdit={onEdit}
            onDelete={onDelete}
            onDuplicate={onDuplicate}
            isVisible={isVisible(s.id)}
            onToggleVisibility={onToggleVisibility}
          />
        ))}
      </div>
    </section>
  );
}

export default function StandardsList({ grouped, onEdit, onDelete, onDuplicate, isVisible, onToggleVisibility }) {
  const all = [...(grouped.builtin || []), ...(grouped.quodeq || []), ...(grouped.community || []), ...(grouped.custom || [])];

  if (all.length === 0) {
    return (
      <div className="standards-empty">
        <p>No standards found. Import from the library or create a custom standard.</p>
      </div>
    );
  }

  return (
    <div className="standards-list">
      <StandardsSection
        title="Standards"
        standards={all}
        onEdit={onEdit}
        onDelete={onDelete}
        onDuplicate={onDuplicate}
        isVisible={isVisible}
        onToggleVisibility={onToggleVisibility}
      />
    </div>
  );
}
