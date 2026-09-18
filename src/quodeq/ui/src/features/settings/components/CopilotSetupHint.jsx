import { tRich } from '../../../strings/rich.jsx';

export default function CopilotSetupHint({ children }) {
  return (
    <div className="settings-row">
      <div className="settings-install-hint settings-copilot-setup">
        {tRich('settings.copilotSetup')}
        {children}
      </div>
    </div>
  );
}
