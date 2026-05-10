/**
 * Test-only stand-in for the browser `EventSource` API.
 *
 * Assign to `global.EventSource` in a test's `beforeEach` so hooks under test
 * pick it up instead of the real implementation. The most recently constructed
 * instance is recorded on `MockEventSource.last`, so tests can grab it without
 * threading the reference through the hook. Use `emit(name, dataObj)` to fire
 * a named event synchronously — `dataObj` is JSON-stringified into `event.data`
 * and its `id` (if any) is exposed as `event.lastEventId`, mirroring the real
 * SSE message shape.
 */
export class MockEventSource {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    MockEventSource.last = this;
  }
  addEventListener(event, handler) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(handler);
  }
  close() { this.closed = true; }
  emit(event, data) {
    (this.listeners[event] || []).forEach((h) =>
      h({ data: JSON.stringify(data), lastEventId: data?.id }),
    );
  }
}
