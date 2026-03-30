import StandardCard from './StandardCard.jsx';

function SectionHeader({ title, count }) {
  return (
    <div className="standards-section-header">
      <h2 className="standards-section-title">{title}</h2>
      <span className="standards-section-count">{count}</span>
    </div>
  );
}

function StandardsSection({ title, standards, onEdit, onDelete, onDuplicate }) {
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
          />
        ))}
      </div>
    </section>
  );
}

export default function StandardsList({ grouped, onEdit, onDelete, onDuplicate }) {
  const total = (grouped.builtin?.length ?? 0) + (grouped.community?.length ?? 0) + (grouped.custom?.length ?? 0);

  if (total === 0) {
    return (
      <div className="standards-empty">
        <p>No standards found. Import from the library or create a custom standard.</p>
      </div>
    );
  }

  return (
    <div className="standards-list">
      <StandardsSection
        title="ISO 25010"
        standards={grouped.builtin || []}
        onEdit={onEdit}
        onDelete={onDelete}
        onDuplicate={onDuplicate}
      />
      <StandardsSection
        title="Community"
        standards={grouped.community || []}
        onEdit={onEdit}
        onDelete={onDelete}
        onDuplicate={onDuplicate}
      />
      <StandardsSection
        title="Custom Standards"
        standards={grouped.custom || []}
        onEdit={onEdit}
        onDelete={onDelete}
        onDuplicate={onDuplicate}
      />
    </div>
  );
}
