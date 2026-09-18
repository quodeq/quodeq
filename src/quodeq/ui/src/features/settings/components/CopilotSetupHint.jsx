import { tRich } from '../../../strings/rich.jsx';

export default function CopilotSetupHint() {
  return (
    <div className="settings-row">
      <div className="settings-install-hint settings-copilot-setup">{tRich('settings.copilotSetup')}</div>
    </div>
  );
}
