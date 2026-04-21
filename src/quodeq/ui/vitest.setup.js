import '@testing-library/jest-dom/vitest';

// Stub window.matchMedia — not implemented in JSDOM but required by xterm.js
window.matchMedia = window.matchMedia || function matchMedia(query) {
  return {
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  };
};

// Stub HTMLCanvasElement.getContext — not implemented in JSDOM
HTMLCanvasElement.prototype.getContext = HTMLCanvasElement.prototype.getContext || function () {
  return null;
};

// Stub localStorage — not always present in JSDOM worker threads
if (typeof localStorage === 'undefined' || typeof localStorage.getItem !== 'function') {
  const store = {};
  global.localStorage = {
    getItem: (k) => store[k] ?? null,
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
    clear: () => { Object.keys(store).forEach(k => delete store[k]); },
  };
}
