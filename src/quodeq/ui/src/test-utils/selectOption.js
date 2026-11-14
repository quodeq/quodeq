import { fireEvent, screen, waitFor } from '@testing-library/react';
import { KEY } from '../vocab/keyboard.js';

const ARIA_TRUE = 'true';
const firstSelect = () => screen.getAllByRole('combobox')[0];

/** Opens the Select (by default the first on the page) and finds an option, waiting for it to load. */
export function findSelectOption(name, getSelect = firstSelect) {
  return waitFor(() => {
    const select = getSelect();
    if (select.getAttribute('aria-expanded') !== ARIA_TRUE) fireEvent.click(select);
    return screen.getByRole('option', { name });
  });
}

/** Waits for a Select's option to load, leaving the list closed again. */
export async function waitForSelectOption(name, getSelect = firstSelect) {
  await findSelectOption(name, getSelect);
  fireEvent.keyDown(getSelect(), { key: KEY.ESCAPE });
}

/** Opens a Select whose options are already there and clicks one. */
export function pickSelectOption(select, name) {
  fireEvent.click(select);
  fireEvent.click(screen.getByRole('option', { name }));
}
