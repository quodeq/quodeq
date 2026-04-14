import { useState, useEffect } from 'react';
import { ICON_OVERVIEW, ICON_VIOLATIONS, ICON_MAP, ICON_HISTORY, ICON_EVALUATE, ICON_PROJECTS, ICON_SETTINGS, ICON_STANDARDS, ICON_HELP } from '../constants/navigation.jsx';
import { ACTIVE_PROVIDER_KEY, providerKey, SETTINGS_DOT_DISMISSED_KEY, EVALUATE_DOT_DISMISSED_KEY } from '../constants.js';

const SETUP_POLL_INTERVAL_MS = 2000;

function useSetupStatus() {
  const [status, setStatus] = useState({ needsSettings: false, readyToEvaluate: false });

  useEffect(() => {
    function check() {
      const settingsDismissed = localStorage.getItem(SETTINGS_DOT_DISMISSED_KEY);
      const evaluateDismissed = localStorage.getItem(EVALUATE_DOT_DISMISSED_KEY);
      const provider = localStorage.getItem(ACTIVE_PROVIDER_KEY) || '';
      const model = provider ? localStorage.getItem(providerKey(provider, 'model')) || '' : '';
      const configured = !!(provider && model);

      const showSettings = !settingsDismissed;
      setStatus({
        needsSettings: showSettings,
        readyToEvaluate: !showSettings && configured && !evaluateDismissed,
      });
    }
    check();
    window.addEventListener('storage', check);
    const interval = setInterval(check, SETUP_POLL_INTERVAL_MS);
    return () => { window.removeEventListener('storage', check); clearInterval(interval); };
  }, []);

  return status;
}

function Logo() {
  return (
    <svg viewBox="288 209 965 588" role="img" aria-label="Quodeq" width="36" height="36" style={{overflow:'visible'}}>
      <defs>
        <filter id="chevron-glow" x="-25%" y="-25%" width="150%" height="150%">
          <feDropShadow dx="0" dy="0" stdDeviation="6" floodColor="var(--logo-chevron-hover)" floodOpacity="0.28" />
        </filter>
        <mask id="needle-hole-mask">
          <rect width="1536" height="1024" fill="#fff" />
          <circle cx="768" cy="502" r="31" fill="#000" />
        </mask>
      </defs>
      <path id="left-chevron" d="M4542 7154 c-29 -14 -68 -45 -87 -68 -18 -22 -109 -135 -201 -251 -92 -115 -229 -286 -304 -380 -75 -93 -262 -327 -415 -520 -153 -192 -299 -375 -323 -405 -62 -77 -84 -125 -90 -195 -6 -79 17 -158 61 -210 18 -22 161 -202 317 -400 156 -198 324 -412 374 -475 131 -165 195 -245 336 -424 237 -301 295 -370 338 -401 l44 -30 255 -3 c288 -3 303 0 303 61 0 32 -21 62 -405 557 -49 63 -159 205 -245 316 -164 213 -528 680 -620 796 -83 106 -100 137 -99 188 0 58 13 86 76 162 28 35 181 225 340 423 158 199 440 550 626 781 247 310 337 428 337 447 0 53 -19 57 -305 57 l-261 0 -52 -26z" transform="translate(0 1024) scale(0.1 -0.1)" style={{fill:'var(--logo-chevron)',cursor:'pointer',transition:'fill 180ms ease, filter 180ms ease'}} />
      <path id="right-chevron" d="M10234 7155 c-19 -19 -23 -31 -18 -48 8 -26 -11 -3 354 -447 155 -190 346 -424 425 -520 137 -170 359 -439 529 -646 92 -110 111 -153 102 -219 -7 -45 -2 -38 -511 -685 -152 -193 -608 -777 -719 -920 -27 -36 -71 -92 -98 -125 -35 -43 -48 -68 -48 -92 0 -60 14 -63 290 -63 244 0 246 0 298 26 28 14 64 40 79 58 31 36 531 667 658 831 44 56 206 261 360 454 154 194 292 371 308 394 34 51 47 97 47 163 0 109 39 55 -653 904 -34 41 -140 172 -236 290 -97 118 -218 267 -269 330 -52 63 -124 152 -160 198 -53 66 -78 89 -126 112 l-59 30 -264 0 -264 0 -25 -25z" transform="translate(0 1024) scale(0.1 -0.1)" style={{fill:'var(--logo-chevron)',cursor:'pointer',transition:'fill 180ms ease, filter 180ms ease'}} />
      <path d="M7347 7895 c-421 -51 -848 -208 -1192 -437 -514 -342 -923 -889 -1083 -1449 -82 -285 -107 -484 -99 -789 6 -255 21 -365 77 -586 50 -195 94 -313 190 -509 212 -432 526 -792 922 -1055 713 -474 1602 -586 2428 -305 89 30 100 31 149 5 166 -84 533 -188 821 -231 158 -24 466 -31 613 -16 l79 9 -39 26 c-104 69 -293 257 -411 409 -90 116 -252 354 -252 370 0 6 6 13 14 16 22 9 237 254 320 366 221 297 383 652 456 996 36 170 50 293 56 485 23 701 -228 1336 -732 1860 -442 458 -1035 753 -1677 835 -145 18 -487 18 -640 0z m643 -551 c628 -93 1210 -469 1534 -994 143 -230 235 -481 283 -769 24 -146 24 -443 -1 -601 -83 -527 -331 -972 -731 -1310 -230 -194 -532 -349 -830 -426 -180 -46 -294 -63 -475 -70 -360 -15 -699 57 -1025 215 -426 208 -750 530 -966 957 -254 505 -298 1067 -122 1594 44 132 153 357 230 475 294 447 746 764 1278 894 249 61 561 74 825 35z" transform="translate(0 1024) scale(0.1 -0.1)" fillRule="evenodd" style={{fill:'var(--logo-q)'}} />
      <g mask="url(#needle-hole-mask)">
        <path d="M 640.21436,652.66711 721.35247,466.18696 899.84338,349.64453 c -87.009,100.60868 -173.29796,201.83295 -259.62902,303.02258 z" style={{fill:'var(--logo-needle)'}} />
        <path d="M 640.21436,652.66711 810.38705,542.33876 899.84338,349.64453 c -87.009,100.60868 -173.29796,201.83295 -259.62902,303.02258 z" style={{fill:'var(--logo-needle-dark)'}} />
      </g>
    </svg>
  );
}

function NavButton({ id, label, icon, activeTab, onNavTab, showDot }) {
  return (
    <button
      type="button"
      className={`sidebar-nav-item${activeTab === id ? ' active' : ''}`}
      onClick={() => onNavTab(id)}
      title={label}
    >
      {icon}
      <span className="sidebar-nav-label">{label}</span>
      {showDot && <span className="sidebar-nav-dot" />}
    </button>
  );
}

export default function Sidebar({ activeTab, onNavTab }) {
  const { needsSettings, readyToEvaluate } = useSetupStatus();

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-brand-icon">
          <Logo />
        </div>
        <span className="sidebar-brand-text">quodeq</span>
      </div>

      <nav className="sidebar-nav">
        <NavButton id="overview" label="Overview" icon={ICON_OVERVIEW} activeTab={activeTab} onNavTab={onNavTab} />
        <NavButton id="violations" label="Violations" icon={ICON_VIOLATIONS} activeTab={activeTab} onNavTab={onNavTab} />
        <NavButton id="map" label="Map" icon={ICON_MAP} activeTab={activeTab} onNavTab={onNavTab} />
        <NavButton id="history" label="History" icon={ICON_HISTORY} activeTab={activeTab} onNavTab={onNavTab} />
        <NavButton id="evaluate" label="Evaluate" icon={ICON_EVALUATE} activeTab={activeTab} onNavTab={(id) => { try { localStorage.setItem(EVALUATE_DOT_DISMISSED_KEY, '1'); } catch {} onNavTab(id); }} showDot={readyToEvaluate} />
        <NavButton id="standards" label="Standards" icon={ICON_STANDARDS} activeTab={activeTab} onNavTab={onNavTab} />
        <NavButton id="projects" label="Projects" icon={ICON_PROJECTS} activeTab={activeTab} onNavTab={onNavTab} />
      </nav>

      <div className="sidebar-bottom-nav">
        <NavButton id="help" label="Help" icon={ICON_HELP} activeTab={activeTab} onNavTab={onNavTab} />
        <NavButton id="settings" label="Settings" icon={ICON_SETTINGS} activeTab={activeTab} onNavTab={(id) => { try { localStorage.setItem(SETTINGS_DOT_DISMISSED_KEY, '1'); } catch {} onNavTab(id); }} showDot={needsSettings} />
      </div>
    </aside>
  );
}
