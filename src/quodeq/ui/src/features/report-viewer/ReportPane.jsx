import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useReportViewer } from './ReportViewerContext.jsx';
import { ReportMarkdown } from './markdownRenderer.jsx';
import { clampPaneWidth } from './resizeMath.js';
import './ReportPane.css';

function slugify(s) {
  return (s || 'report').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'report';
}

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
}

function downloadMarkdown(title, markdown) {
  const filename = `${slugify(title)}-${todayISO()}.md`;

  // Inside pywebview, blob-URL downloads get handed off to the OS as a
  // viewer instead of saved to disk. Use the Python-side native Save dialog
  // when it's available.
  const pyApi = typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
  if (pyApi && typeof pyApi.save_file === 'function') {
    pyApi.save_file(markdown, filename);
    return;
  }

  // Browser path: anchor-driven blob download. UTF-8 BOM so text viewers
  // detect encoding correctly if the file ends up displayed instead of saved.
  const blob = new Blob(['﻿', markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  // Defer cleanup so the browser has time to start the download before
  // we revoke the blob URL — synchronous cleanup races and can drop the file.
  setTimeout(() => {
    a.remove();
    URL.revokeObjectURL(url);
  }, 0);
}

class RenderBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { /* swallow — header still works */ }
  componentDidUpdate(prev) {
    if (prev.contentKey !== this.props.contentKey && this.state.failed) {
      this.setState({ failed: false });
    }
  }
  render() {
    if (this.state.failed) {
      return <p className="report-pane__error">Failed to render report.</p>;
    }
    return this.props.children;
  }
}

// Defer mounting the markdown body until after the column slide-in finishes
// (~220ms transition). Otherwise the heavy DOM work happens mid-animation
// and the slide stutters.
const SLIDE_MS = 220;
const COPY_FEEDBACK_MS = 1500;

export function ReportPane() {
  const { current, isOpen, paneWidth, setPaneWidth, closeReport } = useReportViewer();
  const bodyRef = useRef(null);
  const [bodyReady, setBodyReady] = useState(false);
  const [justCopied, setJustCopied] = useState(false);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  }, [current]);

  useEffect(() => {
    if (!isOpen || !current) {
      setBodyReady(false);
      return undefined;
    }
    setBodyReady(false);
    const id = setTimeout(() => setBodyReady(true), SLIDE_MS);
    return () => clearTimeout(id);
  }, [isOpen, current]);

  // Reset the copied indicator any time the report content changes.
  useEffect(() => { setJustCopied(false); }, [current]);

  const onCopy = useCallback(() => {
    if (!current) return;
    navigator.clipboard?.writeText(current.markdown);
    setJustCopied(true);
  }, [current]);

  useEffect(() => {
    if (!justCopied) return undefined;
    const id = setTimeout(() => setJustCopied(false), COPY_FEEDBACK_MS);
    return () => clearTimeout(id);
  }, [justCopied]);

  const onDownload = useCallback(() => {
    if (current) downloadMarkdown(current.title, current.markdown);
  }, [current]);

  const onDividerPointerDown = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = paneWidth;
    const viewport = window.innerWidth;
    const onMove = (ev) => {
      const delta = startX - ev.clientX; // dragging left grows the pane
      const next = clampPaneWidth(startWidth + delta, viewport);
      document.documentElement.style.setProperty('--report-pane-width', `${next}px`);
    };
    const onUp = (ev) => {
      const delta = startX - ev.clientX;
      const next = clampPaneWidth(startWidth + delta, window.innerWidth);
      setPaneWidth(next);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [paneWidth, setPaneWidth]);

  if (!isOpen || !current) return null;

  return (
    <aside
      className="report-pane"
      role="complementary"
      aria-label="Report viewer"
    >
      <div
        className="report-pane__divider"
        role="separator"
        aria-orientation="vertical"
        onPointerDown={onDividerPointerDown}
      />
      <header className="report-pane__header">
        <h2 className="report-pane__title" title={current.title}>{current.title}</h2>
        <div className="report-pane__actions">
          <button
            type="button"
            className={`report-pane__icon-btn${justCopied ? ' report-pane__icon-btn--ok' : ''}`}
            onClick={onCopy}
            aria-label={justCopied ? 'Copied' : 'Copy as Markdown'}
            title={justCopied ? 'Copied' : 'Copy as Markdown'}
          >{justCopied ? '✓' : '⧉'}</button>
          <button type="button" className="report-pane__icon-btn" onClick={onDownload} aria-label="Download .md" title="Download .md">↓</button>
          <button type="button" className="report-pane__icon-btn" onClick={closeReport} aria-label="Close report" title="Close">✕</button>
        </div>
      </header>
      <div className="report-pane__body" ref={bodyRef}>
        {bodyReady ? (
          <RenderBoundary contentKey={current?.title}>
            <ReportMarkdown markdown={current.markdown} />
          </RenderBoundary>
        ) : (
          <div className="report-pane__body-skeleton" aria-hidden="true">
            <span /><span /><span />
          </div>
        )}
      </div>
    </aside>
  );
}
