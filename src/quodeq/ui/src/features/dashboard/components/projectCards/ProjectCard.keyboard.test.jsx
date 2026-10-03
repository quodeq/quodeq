import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ProjectCard } from './ProjectCard.jsx';

const PROJECT = { id: 'p1', name: 'demo', onboardingCompletedAt: null, runsCount: 1 };

function renderCard() {
  const onSelect = vi.fn();
  const onResumeSetup = vi.fn();
  render(<ProjectCard project={PROJECT} cardProps={{ onSelect, onResumeSetup }} />);
  const resume = screen.getByRole('button', { name: 'Resume setup' });
  const card = resume.closest('.project-card-main');
  return { onSelect, onResumeSetup, resume, card };
}

describe('ProjectCard keyboard handling', () => {
  it('selects the project on Enter on the card itself', () => {
    const { onSelect, card } = renderCard();
    const notPrevented = fireEvent.keyDown(card, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('p1');
    expect(notPrevented).toBe(false);
  });

  it.each(['Enter', ' '])('leaves %j on the nested resume button to the button', (key) => {
    const { onSelect, resume } = renderCard();
    const notPrevented = fireEvent.keyDown(resume, { key });
    expect(onSelect).not.toHaveBeenCalled();
    expect(notPrevented).toBe(true);
  });

  it('clicking the resume button calls onResumeSetup only', () => {
    const { onSelect, onResumeSetup, resume } = renderCard();
    fireEvent.click(resume);
    expect(onResumeSetup).toHaveBeenCalledWith('p1');
    expect(onSelect).not.toHaveBeenCalled();
  });
});
