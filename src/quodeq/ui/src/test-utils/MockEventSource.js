/**
 * Test-only stand-in for the browser `EventSource` API.
 *
 * Assign to `global.EventSource` in a test's `beforeEach` so hooks under test
 * pick it up instead of the real implementation. The most recently constructed
 * instance is recorded on `MockEventSource.last`, so tests can grab it without
 * threading the reference through the hook. Use `emit(name, dataObj)` to fire
 * a named event synchronously — `dataObj` is JSON-stringified into `event.data`
 * and its `id` (if any) is exposed as `event.lastEventId`, mirroring the real
 * SSE message shape. Every instance is also pushed onto
 * `MockEventSource.instances` (reset it in `beforeEach`) so tests can count
 * how many connections a render opened. `fail()` drives the `onerror` path
 * the way a dropped connection would.
 */
export class MockEventSource {
  static instances = [];
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.readyState = MockEventSource.CONNECTING;
    MockEventSource.last = this;
    MockEventSource.instances.push(this);
  }
  open() {
    this.readyState = MockEventSource.OPEN;
    this.onopen?.({});
  }
  fail() {
    this.readyState = MockEventSource.CONNECTING;
    this.onerror?.({});
  }
  addEventListener(event, handler) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(handler);
  }
  close() { this.closed = true; this.readyState = MockEventSource.CLOSED; }
  emit(event, data) {
    (this.listeners[event] || []).forEach((h) =>
      h({ data: JSON.stringify(data), lastEventId: data?.id }),
    );
  }
}
