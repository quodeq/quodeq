import { createContext, useContext } from 'react';
import * as api from './index.js';

const ApiContext = createContext(api);

export const ApiProvider = ({ value, children }) => (
  <ApiContext.Provider value={value || api}>{children}</ApiContext.Provider>
);

export function useApi() {
  return useContext(ApiContext);
}

export { ApiContext };
export default ApiContext;
