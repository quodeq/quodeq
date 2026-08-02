import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { t } from '../../strings/index.js';

const components = {
  a: ({ node, ...props }) => (
    <a {...props} target="_blank" rel="noopener noreferrer" />
  ),
  table: ({ node, ...props }) => (
    <div className="md-table-wrap">
      <table {...props} />
    </div>
  ),
};

export function ReportContent({ markdown, emptyMessage = t('sidePane.noContent') }) {
  if (!markdown || !markdown.trim()) {
    return <p className="side-pane-md side-pane-md--empty">{emptyMessage}</p>;
  }
  return (
    <div className="side-pane-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
