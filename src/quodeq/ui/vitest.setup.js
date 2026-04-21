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
