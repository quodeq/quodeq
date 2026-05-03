import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import WelcomeStep from './WelcomeStep.jsx';

describe('WelcomeStep', () => {
  it('renders the welcome headline and pitch', () => {
    render(<WelcomeStep onStart={() => {}} onSkip={() => {}} />);
    expect(screen.getByRole('heading', { name: /welcome to quodeq/i })).toBeInTheDocument();
    expect(screen.getByText(/audit code quality/i)).toBeInTheDocument();
  });

  it('calls onStart when Get started is clicked', () => {
    const onStart = vi.fn();
    render(<WelcomeStep onStart={onStart} onSkip={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /get started/i }));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('calls onSkip when Maybe later is clicked', () => {
    const onSkip = vi.fn();
    render(<WelcomeStep onStart={() => {}} onSkip={onSkip} />);
    fireEvent.click(screen.getByRole('button', { name: /maybe later/i }));
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it('renders the three preview rows', () => {
    render(<WelcomeStep onStart={() => {}} onSkip={() => {}} />);
    expect(screen.getByText(/connect repo/i)).toBeInTheDocument();
    expect(screen.getByText(/pick ai provider/i)).toBeInTheDocument();
    expect(screen.getByText(/pick a standard/i)).toBeInTheDocument();
  });
});
