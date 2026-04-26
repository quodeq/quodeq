import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useReportViewer } from './ReportViewerContext.jsx';
import './ReportSplitButton.css';

function slugify(s) {
  return (s || 'report').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'report';
}
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
}
function downloadMarkdown(title, markdown) {
  const blob = new Blob([markdown], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${slugify(title)}-${todayISO()}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function ReportSplitButton({ label = 'Report', title, buildMarkdown, className = '', icon = null }) {
  const { openReport } = useReportViewer();
  const [menuOpen, setMenuOpen] = useState(false);
  const containerRef = useRef(null);

  const onMain = useCallback(() => {
    openReport({ title, markdown: buildMarkdown() });
  }, [openReport, title, buildMarkdown]);

  const onCopy = useCallback(() => {
    navigator.clipboard?.writeText(buildMarkdown());
    setMenuOpen(false);
  }, [buildMarkdown]);

  const onDownload = useCallback(() => {
    downloadMarkdown(title, buildMarkdown());
    setMenuOpen(false);
  }, [title, buildMarkdown]);

  useEffect(() => {
    if (!menuOpen) return undefined;
    function onDocClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) setMenuOpen(false);
    }
    function onKey(e) { if (e.key === 'Escape') setMenuOpen(false); }
    document.addEventListener('mousedown', onDocClick);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      window.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  return (
    <div ref={containerRef} className={`report-split ${className}`}>
      <button type="button" className="report-split__main" onClick={onMain}>
        {icon}
        <span>{label}</span>
      </button>
      <button
        type="button"
        className="report-split__chevron"
        onClick={() => setMenuOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        aria-label="More report actions"
      >▾</button>
      {menuOpen && (
        <div role="menu" className="report-split__menu">
          <button type="button" role="menuitem" className="report-split__item" onClick={onCopy}>Copy as Markdown</button>
          <button type="button" role="menuitem" className="report-split__item" onClick={onDownload}>Download .md</button>
        </div>
      )}
    </div>
  );
}
