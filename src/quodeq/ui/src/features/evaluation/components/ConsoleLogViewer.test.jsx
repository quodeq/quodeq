import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import ConsoleLogViewer from './ConsoleLogViewer.jsx';

const rowNodes = (container) => [...container.querySelectorAll('.console-log-line')];
const rowTexts = (container) => rowNodes(container).map((n) => n.textContent);

describe('ConsoleLogViewer', () => {
  it('keeps surviving row DOM nodes across a front trim (stable keys)', () => {
    const { container, rerender } = render(<ConsoleLogViewer logs={['a', 'b', 'c']} firstSeq={0} />);
    const bNode = rowNodes(container)[1];
    rerender(<ConsoleLogViewer logs={['b', 'c', 'd']} firstSeq={1} />);
    expect(rowTexts(container)).toEqual(['b', 'c', 'd']);
    expect(rowNodes(container)[0]).toBe(bNode);
  });

  it('dedupes identical heartbeat lines across batches', () => {
    const { container, rerender } = render(<ConsoleLogViewer logs={['hb', 'hb']} firstSeq={0} />);
    rerender(<ConsoleLogViewer logs={['hb', 'hb', 'hb', 'x']} firstSeq={0} />);
    expect(rowTexts(container)).toEqual(['hb', 'x']);
  });

  it('drops the old rows when the source resets', () => {
    const { container, rerender } = render(<ConsoleLogViewer logs={['old1', 'old2']} firstSeq={0} />);
    rerender(<ConsoleLogViewer logs={['new']} firstSeq={2} />);
    expect(rowTexts(container)).toEqual(['new']);
  });

  it('renders the trailer last even when a late batch lands after it', () => {
    const { container, rerender } = render(
      <ConsoleLogViewer logs={['a']} firstSeq={0} trailer="evaluation cancelled" />,
    );
    rerender(<ConsoleLogViewer logs={['a', 'late']} firstSeq={0} trailer="evaluation cancelled" />);
    expect(rowTexts(container)).toEqual(['a', 'late', 'evaluation cancelled']);
  });

  it('still works for a caller that passes no firstSeq', () => {
    const { container, rerender } = render(<ConsoleLogViewer logs={['\x1b[0;34mhi\x1b[0m']} />);
    rerender(<ConsoleLogViewer logs={['\x1b[0;34mhi\x1b[0m', 'there']} />);
    expect(rowTexts(container)).toEqual(['hi', 'there']);
  });

  it('shows the waiting message with no lines and no trailer', () => {
    const { container } = render(<ConsoleLogViewer logs={[]} firstSeq={0} />);
    expect(container.querySelector('.console-log-empty')).not.toBeNull();
  });

  it('drops stale rows when sourceId changes even if the new source reuses the old seq range', () => {
    // A source swap (job switch, provider identity change) can hand out a
    // fresh stream whose own firstSeq/length pair looks, by pure numeric
    // coincidence, like a valid continuation of the old one (e.g. both
    // start at 0 with the new source ending up longer). Without sourceId
    // the pipeline would splice the new source's tail onto the old source's
    // head; with it, a change forces a full rebuild instead.
    const { container, rerender } = render(
      <ConsoleLogViewer logs={['a', 'b']} firstSeq={0} sourceId="job-a" />,
    );
    expect(rowTexts(container)).toEqual(['a', 'b']);
    rerender(<ConsoleLogViewer logs={['x', 'y', 'z']} firstSeq={0} sourceId="job-b" />);
    expect(rowTexts(container)).toEqual(['x', 'y', 'z']);
  });
});
