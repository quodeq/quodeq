import React from 'react';
import { ReportContent } from './reportContent.jsx';
import { buildSingleViolationPlanText } from '../../utils/planBuilder.js';

function slugify(s) {
  return (s || 'violation').replace(/[^a-z0-9-]+/gi, '-').toLowerCase().replace(/^-|-$/g, '') || 'violation';
}

/**
 * Build a side-pane window spec for a single violation's fix plan.
 *
 * @param {Object} v   Violation object (severity, principle, file, line, ...).
 * @param {string} [titleOverride]  Title shown in the window header. Defaults
 *                                  to "<dimension> / <principle>" or the
 *                                  principle name when no dimension is set.
 */
export function violationFixPlanSpec(v, titleOverride) {
  if (!v) return null;
  const heading = titleOverride
    || [v.dimension, v.principle].filter(Boolean).join(' / ')
    || 'Violation';
  const buildMarkdown = () => buildSingleViolationPlanText(v, heading, {
    reqRefs: v.reqRefs,
    reqFallback: v.req || undefined,
  });
  const fileRef = v.file ? `${v.file}${v.line != null ? `:${v.line}` : ''}` : 'unknown';
  const slug = slugify(`${v.principle || 'violation'}-${fileRef}`);
  return {
    id: `fixplan:violation:${slug}`,
    type: 'fixplan-violation',
    title: `${heading} fix plan`,
    render: () => <ReportContent markdown={buildMarkdown()} />,
    copy: () => buildMarkdown(),
    download: () => ({ filename: `violation-${slug}-fix-plan.md`, body: buildMarkdown() }),
  };
}
