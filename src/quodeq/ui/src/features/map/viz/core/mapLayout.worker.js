import { handlePackMessage } from './packLayout.js';

self.onmessage = (event) => {
  const reply = handlePackMessage(event.data);
  self.postMessage(reply, [reply.xyr.buffer]);
};
