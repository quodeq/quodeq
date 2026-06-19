import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const COPY_FEEDBACK_MS = 1500;
// Defer mounting the body until the slide-in animation finishes (~220ms).
// Otherwise the heavy markdown render happens mid-animation and stutters.
const SLIDE_MS = 220;

function slugify(s) {
  return (s || 'window').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'window';
}

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
}

function triggerDownload({ filename, body }) {
  const safeName = filename || `${slugify(body?.slice(0, 32))}-${todayISO()}.md`;
  const pyApi = typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
  if (pyApi && typeof pyApi.save_file === 'function') {
    pyApi.save_file(body, safeName);
    return;
  }
  const blob = new Blob(['﻿', body], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = safeName; a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 0);
}

class RenderBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error, info) { console.error('[SidePaneWindow] render error:', error, info); }
  componentDidUpdate(prev) {
    if (prev.contentKey !== this.props.contentKey && this.state.failed) {
      this.setState({ failed: false });
    }
  }
  render() {
    if (this.state.failed) {
      return <p className="side-pane-window__error">Failed to render report.</p>;
    }
    return this.props.children;
  }
}

export function SidePaneWindow({ spec, onClose }) {
  const bodyRef = useRef(null);
  const [justCopied, setJustCopied] = useState(false);
  const [bodyReady, setBodyReady] = useState(false);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  }, [spec.id]);

  useEffect(() => { setJustCopied(false); }, [spec.id]);

  // Defer the body mount on each fresh window; the skeleton holds the slot
  // while the parent's slide-in finishes.
  useEffect(() => {
    setBodyReady(false);
    const t = setTimeout(() => setBodyReady(true), SLIDE_MS);
    return () => clearTimeout(t);
  }, [spec.id]);

  useEffect(() => {
    if (!justCopied) return undefined;
    const t = setTimeout(() => setJustCopied(false), COPY_FEEDBACK_MS);
    return () => clearTimeout(t);
  }, [justCopied]);

  const onCopy = useCallback(() => {
    if (!spec.copy) return;
    navigator.clipboard?.writeText(spec.copy());
    setJustCopied(true);
  }, [spec]);

  const onDownload = useCallback(() => {
    if (!spec.download) return;
    triggerDownload(spec.download());
  }, [spec]);

  const onClickClose = useCallback(() => onClose(spec.id), [onClose, spec.id]);

  // Memoise the rendered body keyed on spec identity. Prevents the heavy
  // markdown subtree from re-running through React reconciliation every
  // time the parent (SidePane) re-renders for unrelated reasons — e.g.
  // a sibling window resize updating the inline flex weights of the slots.
  const body = useMemo(() => spec.render(), [spec]);

  return (
    <section className="side-pane-window" aria-label={spec.title}>
      <header className="side-pane-window__header">
        <h2 className="side-pane-window__title" title={spec.title}>{spec.title}</h2>
        <div className="side-pane-window__actions">
          {spec.copy && (
            <button
              type="button"
              className={`side-pane-window__icon-btn${justCopied ? ' side-pane-window__icon-btn--ok' : ''}`}
              onClick={onCopy}
              aria-label={justCopied ? 'Copied' : 'Copy'}
              title={justCopied ? 'Copied' : 'Copy'}
            >{justCopied ? '✓' : '⧉'}</button>
          )}
          {spec.download && (
            <button
              type="button"
              className="side-pane-window__icon-btn"
              onClick={onDownload}
              aria-label="Download"
              title="Download"
            >↓</button>
          )}
          <button
            type="button"
            className="side-pane-window__icon-btn"
            onClick={onClickClose}
            aria-label="Close window"
            title="Close window"
          >✕</button>
        </div>
      </header>
      <div className="side-pane-window__body" ref={bodyRef}>
        {bodyReady ? (
          <RenderBoundary contentKey={spec.id}>{body}</RenderBoundary>
        ) : (
          <div className="side-pane-window__body-skeleton" aria-hidden="true">
            <span /><span /><span />
          </div>
        )}
      </div>
    </section>
  );
}
