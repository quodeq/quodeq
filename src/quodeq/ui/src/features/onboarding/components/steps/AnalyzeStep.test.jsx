import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import AnalyzeStep from './AnalyzeStep.jsx';
import { useWizardState } from '../../hooks/useWizardState.js';
import { STEP_ANALYZE } from '../../wizardSteps.js';

vi.mock('../../../../api/index.js', () => ({ getProviderConfigs: vi.fn(async () => ({})) }));
vi.mock('../../../settings/components/ProviderTabs.jsx', () => ({
  default: () => <div data-testid="provider-tabs-stub" />,
}));
// The folder browser is its own modal with its own fetches; here a pick
// resolves with whatever the test queued.
const picks = vi.hoisted(() => ({ next: null }));
vi.mock('../../../dashboard/hooks/useFolderPicker.jsx', () => ({
  useFolderPicker: () => ({ browseFolder: async () => picks.next, picker: null }),
}));

const standards = [{ id: 'default', name: 'quodeq default standard', dimensions: ['security', 'maintainability', 'performance', 'reliability', 'usability', 'flexibility'] }];
const claudeDetected = async () => [{ id: 'claude-code', classification: 'cli', detected: true, defaultModel: 'claude-sonnet-5-5' }];

function writeActiveProviderState({ id, model }) {
  localStorage.setItem('cc-active-provider', id);
  localStorage.setItem(`cc-${id}-model`, model);
}

// The step against a live wizard state, the way OnboardingStepSwitch mounts it.
function Analyze(props) {
  const wizard = useWizardState({ initial: { step: STEP_ANALYZE } });
  return <AnalyzeStep state={wizard.state} actions={wizard} standards={standards} onLaunch={() => {}} {...props} />;
}

describe('AnalyzeStep', () => {
  let user;
  beforeEach(() => {
    localStorage.clear();
    picks.next = null;
    user = userEvent.setup();
  });

  it('first run: detected provider is recommended, default standard shown, run disabled until a repo is typed', async () => {
    render(<Analyze detect={claudeDetected} />);
    expect(await screen.findByText('found · recommended')).toBeInTheDocument();
    expect(screen.getByText('Claude Code')).toBeInTheDocument();
    expect(screen.getByText('quodeq default standard')).toBeInTheDocument();
    expect(screen.getByText(/security, maintainability, performance/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'scan and run' })).toBeDisabled();
    await user.type(screen.getByRole('textbox', { name: 'repository' }), 'https://github.com/acme/billing.git');
    expect(screen.getByText(/quodeq keeps a working copy in .*quodeq\/repos\/billing/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'scan and run' })).toBeEnabled();
  });

  it('returning user: one summary line, the drawer stays closed until change', async () => {
    writeActiveProviderState({ id: 'claude', model: 'claude-sonnet-5-5' });
    render(<Analyze detect={async () => []} />);
    expect(await screen.findByText('reviewed by Claude Code · against quodeq default standard')).toBeInTheDocument();
    expect(screen.queryByText('Reviewed by')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'change' }));
    expect(screen.getByText('Reviewed by')).toBeInTheDocument();
  });

  it('no model found offers set one up, which opens the provider tabs', async () => {
    render(<Analyze detect={async () => []} />);
    expect(await screen.findByText('no model found on this machine')).toBeInTheDocument();
    expect(screen.queryByTestId('provider-tabs-stub')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'set one up' }));
    expect(screen.getByTestId('provider-tabs-stub')).toBeInTheDocument();
  });

  it('the folder source hides the working-copy note and sends no cloneDest', async () => {
    const onLaunch = vi.fn();
    picks.next = '/Users/me/code/app';
    render(<Analyze detect={claudeDetected} onLaunch={onLaunch} />);
    await screen.findByText('found · recommended');
    await user.click(screen.getByRole('radio', { name: 'choose a local folder' }));
    await user.click(screen.getByRole('button', { name: 'choose a folder' }));
    expect(await screen.findByText('/Users/me/code/app')).toBeInTheDocument();
    expect(screen.queryByText(/quodeq keeps a working copy/)).toBeNull();
    await user.click(screen.getByRole('button', { name: 'scan and run' }));
    expect(onLaunch).toHaveBeenCalledTimes(1);
    const request = onLaunch.mock.calls[0][0];
    expect(request).toMatchObject({ repo: '/Users/me/code/app', source: 'folder', standardIds: ['default'] });
    expect(request).not.toHaveProperty('cloneDest');
  });

  it('a changed working-copy root is sent as cloneDest; the default is not', async () => {
    const onLaunch = vi.fn();
    render(<Analyze detect={claudeDetected} onLaunch={onLaunch} />);
    await screen.findByText('found · recommended');
    await user.type(screen.getByRole('textbox', { name: 'repository' }), 'https://github.com/acme/billing.git');
    await user.click(screen.getByRole('button', { name: 'scan and run' }));
    expect(onLaunch.mock.calls[0][0]).not.toHaveProperty('cloneDest');

    picks.next = '/Volumes/work';
    await user.click(screen.getByRole('button', { name: 'change where the working copy goes' }));
    expect(await screen.findByText(/quodeq keeps a working copy in \/Volumes\/work\/billing/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'scan and run' }));
    expect(onLaunch.mock.calls[1][0]).toMatchObject({ repo: 'https://github.com/acme/billing.git', source: 'url', cloneDest: '/Volumes/work' });
    expect(localStorage.getItem('quodeq.lastCloneRoot')).toBe('/Volumes/work');
  });
});
