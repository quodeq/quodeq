import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ActionPreviewCard } from './ActionPreviewCard.jsx';

const mdComponents = {
  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
  table: ({ node, ...props }) => (
    <div className="md-table-wrap">
      <table {...props} />
    </div>
  ),
};

function MessageItem({ message }) {
  switch (message.role) {
    case 'user':
      return <div className="assistant-msg assistant-msg-user">{message.text}</div>;
    case 'assistant':
      return (
        <div className="assistant-msg assistant-msg-assistant assistant-md">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {message.text}
          </ReactMarkdown>
        </div>
      );
    case 'tool':
      return <div className="assistant-msg assistant-msg-tool">↳ used {message.name}</div>;
    case 'action':
      return (
        <div className="assistant-msg assistant-msg-action">
          <ActionPreviewCard action={message} />
        </div>
      );
    case 'warning':
      return <div className="assistant-msg assistant-msg-warning">{message.message}</div>;
    default:
      return null;
  }
}

/**
 * Renders the assistant conversation transcript. Auto-scrolls to the
 * bottom whenever messages or the streaming indicator change.
 */
export function MessageList({ messages, streaming }) {
  const endRef = useRef(null);

  useEffect(() => {
    // jsdom (unit tests) doesn't implement scrollIntoView — guard for it.
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messages, streaming]);

  return (
    <div className="assistant-messages" role="log" aria-live="polite" aria-relevant="additions">
      {messages.map((message, index) => (
        // Stream messages have no stable id; index is fine since the list
        // only ever grows/mutates its tail (see mergeMessages).
        <MessageItem key={index} message={message} />
      ))}
      {streaming && (
        <div className="assistant-streaming-indicator" role="status" aria-live="polite">
          <span className="assistant-streaming-dot" />
          <span className="assistant-streaming-dot" />
          <span className="assistant-streaming-dot" />
          <span className="sr-only">Assistant is responding…</span>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
