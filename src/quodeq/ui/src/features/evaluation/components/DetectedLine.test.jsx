import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { DetectedLine } from './ReEvaluateCardParts.jsx';

// One count, the files the evaluation will dispatch (the cards count the
// same set), then the languages by name. The scan's per-language counts use
// a different definition of source file, so they would not add up to it.
const scanData = { codeFiles: 3926, languages: { py: 2335, js: 1505 } };

describe('DetectedLine', () => {
  it('one count, what gets evaluated, then the language names', () => {
    render(<DetectedLine scanData={scanData} estimates={{ projectFiles: 3892 }} />);
    const line = document.querySelector('.eval-detected-line');
    expect(line).toHaveTextContent(/^3,892 source files/);
    expect(line).not.toHaveTextContent(/3,926|2,335|1,505/);
    expect(line).toHaveTextContent('python');
  });

  it('falls back to the scan count until the estimates land', () => {
    render(<DetectedLine scanData={scanData} estimates={null} />);
    expect(document.querySelector('.eval-detected-line')).toHaveTextContent(/^3,926 source files/);
  });
});
