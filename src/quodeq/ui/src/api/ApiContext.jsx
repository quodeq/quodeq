import { createContext, useContext } from 'react';
import * as api from './index.js';

const ApiContext = createContext(api);

/**
 * Overrides the API module for everything below it. Tests pass a stub `value`;
 * the app leaves it out and gets the real client.
 */
export const ApiProvider = ({ value, children }) => (
  <ApiContext.Provider value={value || api}>{children}</ApiContext.Provider>
);

/**
 * The API client for the current tree — the real module unless an ApiProvider
 * substituted one.
 */
export function useApi() {
  return useContext(ApiContext);
}

export { ApiContext };
export default ApiContext;
