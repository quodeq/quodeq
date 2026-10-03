import { describe, it, expect } from 'vitest';
import ConsoleLogViewer from '../../evaluation/components/ConsoleLogViewer.jsx';
import { makeProviderLogSpec } from './providerLogSpec.jsx';

const SOURCE = { logs: ['a', 'b'], firstSeq: 7, status: 'done' };

describe('makeProviderLogSpec', () => {
  it('builds the side-pane window for the current stream', () => {
    const buildSpec = makeProviderLogSpec({ windowId: 'demo-log', title: () => 'Demo log' });
    const spec = buildSpec(SOURCE);
    expect(spec.id).toBe('demo-log');
    expect(spec.type).toBe('demo-log');
    expect(spec.title).toBe('Demo log · stopped');
    const el = spec.render();
    expect(el.type).toBe(ConsoleLogViewer);
    expect(el.props).toEqual({ logs: ['a', 'b'], firstSeq: 7 });
  });

  it('suffixes each stream status', () => {
    const buildSpec = makeProviderLogSpec({ windowId: 'demo-log', title: () => 'Demo log' });
    expect(buildSpec({ ...SOURCE, status: 'idle' }).title).toBe('Demo log');
    expect(buildSpec({ ...SOURCE, status: 'streaming' }).title).toBe('Demo log · running');
    expect(buildSpec({ ...SOURCE, status: 'error' }).title).toMatch(/^Demo log.+/);
  });

  it('shows a just-opened window as running with the current buffer', () => {
    const buildSpec = makeProviderLogSpec({ windowId: 'demo-log', title: () => 'Demo log' });
    const spec = buildSpec({ ...SOURCE, status: 'idle' }, { open: true });
    expect(spec.title).toBe('Demo log · running');
    expect(spec.render().props).toEqual({ logs: ['a', 'b'], firstSeq: 7 });
  });

  it('starts a just-opened window from an empty buffer when emptyOnOpen is set', () => {
    const buildSpec = makeProviderLogSpec({ windowId: 'demo-log', title: () => 'Demo log', emptyOnOpen: true });
    const spec = buildSpec({ ...SOURCE, status: 'idle' }, { open: true });
    expect(spec.title).toBe('Demo log · running');
    expect(spec.render().props).toEqual({ logs: [], firstSeq: 0 });
    expect(buildSpec(SOURCE).render().props).toEqual({ logs: ['a', 'b'], firstSeq: 7 });
  });
});
