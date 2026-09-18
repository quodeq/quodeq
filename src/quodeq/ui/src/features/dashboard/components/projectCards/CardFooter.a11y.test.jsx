import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { CardFooter } from './CardFooter.jsx';

describe('CardFooter publish error accessibility', () => {
  it('announces the publish error as an alert', () => {
    render(
      <CardFooter
        name="proj-a"
        confirming={null}
        setConfirming={() => {}}
        publishActions={{
          publishState: 'idle',
          publishingProject: null,
          publishError: 'Publish failed: network error',
          publishErrorProject: 'proj-a',
          onPublish: () => {},
        }}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Publish failed: network error');
  });
});
