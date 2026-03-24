import { useState, useEffect, useRef, useCallback } from 'react';

const PHRASES = [
  'evaluate <b>local folders</b> or <b>remote git repositories</b>, no cloning needed',
  'target a <b>subfolder</b> to focus analysis on a specific module or service',
  'run evaluations over time and <b>track quality trends</b> across runs',
  'each finding includes a <b>fix plan</b>, a concrete path to resolve the issue',
  'violations explain <b>what went wrong</b>, why it matters, and <b>how to fix it</b>',
  'findings are mapped to <b>CWE</b> — the industry standard for software weaknesses',
  'dimensions follow <b>ISO 25010</b>, the international standard for software quality',
  'quality covers <b>reliability</b>, <b>security</b>, <b>maintainability</b>, <b>performance</b>, and more',
];

const AUTO_ADVANCE_MS = 7000;
const TRANSITION_MS = 180;

function SafePhrase({ html }) {
  const parts = html.split(/(<b>.*?<\/b>)/g);
  return parts.map((part, i) => {
    const bold = part.match(/^<b>(.*)<\/b>$/);
    return bold ? <strong key={i}>{bold[1]}</strong> : part;
  });
}

function LogoSvg({ leftCls, rightCls, needleWobble, handleLeft, handleRight }) {
  return (
    <svg className="sa-logo" viewBox="288 209 965 588" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <mask id="sa-needle-mask">
          <rect width="1536" height="1024" fill="#fff" />
          <circle cx="768" cy="502" r="31" fill="#000" />
        </mask>
      </defs>
      <path
        className={leftCls}
        d="M4542 7154 c-29 -14 -68 -45 -87 -68 -18 -22 -109 -135 -201 -251 -92 -115 -229 -286 -304 -380 -75 -93 -262 -327 -415 -520 -153 -192 -299 -375 -323 -405 -62 -77 -84 -125 -90 -195 -6 -79 17 -158 61 -210 18 -22 161 -202 317 -400 156 -198 324 -412 374 -475 131 -165 195 -245 336 -424 237 -301 295 -370 338 -401 l44 -30 255 -3 c288 -3 303 0 303 61 0 32 -21 62 -405 557 -49 63 -159 205 -245 316 -164 213 -528 680 -620 796 -83 106 -100 137 -99 188 0 58 13 86 76 162 28 35 181 225 340 423 158 199 440 550 626 781 247 310 337 428 337 447 0 53 -19 57 -305 57 l-261 0 -52 -26z"
        transform="translate(0 1024) scale(0.1 -0.1)"
        onClick={handleLeft}
        style={{ cursor: 'pointer' }}
      />
      <path
        className={rightCls}
        d="M10234 7155 c-19 -19 -23 -31 -18 -48 8 -26 -11 -3 354 -447 155 -190 346 -424 425 -520 137 -170 359 -439 529 -646 92 -110 111 -153 102 -219 -7 -45 -2 -38 -511 -685 -152 -193 -608 -777 -719 -920 -27 -36 -71 -92 -98 -125 -35 -43 -48 -68 -48 -92 0 -60 14 -63 290 -63 244 0 246 0 298 26 28 14 64 40 79 58 31 36 531 667 658 831 44 56 206 261 360 454 154 194 292 371 308 394 34 51 47 97 47 163 0 109 39 55 -653 904 -34 41 -140 172 -236 290 -97 118 -218 267 -269 330 -52 63 -124 152 -160 198 -53 66 -78 89 -126 112 l-59 30 -264 0 -264 0 -25 -25z"
        transform="translate(0 1024) scale(0.1 -0.1)"
        onClick={handleRight}
        style={{ cursor: 'pointer' }}
      />
      <path
        d="M7347 7895 c-421 -51 -848 -208 -1192 -437 -514 -342 -923 -889 -1083 -1449 -82 -285 -107 -484 -99 -789 6 -255 21 -365 77 -586 50 -195 94 -313 190 -509 212 -432 526 -792 922 -1055 713 -474 1602 -586 2428 -305 89 30 100 31 149 5 166 -84 533 -188 821 -231 158 -24 466 -31 613 -16 l79 9 -39 26 c-104 69 -293 257 -411 409 -90 116 -252 354 -252 370 0 6 6 13 14 16 22 9 237 254 320 366 221 297 383 652 456 996 36 170 50 293 56 485 23 701 -228 1336 -732 1860 -442 458 -1035 753 -1677 835 -145 18 -487 18 -640 0z m643 -551 c628 -93 1210 -469 1534 -994 143 -230 235 -481 283 -769 24 -146 24 -443 -1 -601 -83 -527 -331 -972 -731 -1310 -230 -194 -532 -349 -830 -426 -180 -46 -294 -63 -475 -70 -360 -15 -699 57 -1025 215 -426 208 -750 530 -966 957 -254 505 -298 1067 -122 1594 44 132 153 357 230 475 294 447 746 764 1278 894 249 61 561 74 825 35z"
        transform="translate(0 1024) scale(0.1 -0.1)"
        fill="var(--logo-q)"
        fillRule="evenodd"
      />
      <g
        className={needleWobble ? 'sa-needle sa-needle--wobble' : 'sa-needle'}
        mask="url(#sa-needle-mask)"
      >
        <path d="M 640.21436,652.66711 721.35247,466.18696 899.84338,349.64453 c -87.009,100.60868 -173.29796,201.83295 -259.62902,303.02258 z" fill="var(--logo-needle)" />
        <path d="M 640.21436,652.66711 810.38705,542.33876 899.84338,349.64453 c -87.009,100.60868 -173.29796,201.83295 -259.62902,303.02258 z" fill="var(--logo-needle-dark)" />
      </g>
    </svg>
  );
}

function LogoShell({ leftPress, setLeftPress, rightPress, setRightPress, leftCls, rightCls, needleWobble, handleLeft, handleRight }) {
  return (
    <div className="sa-logo-shell">
      <button
        type="button"
        className="sa-hit sa-hit--left"
        tabIndex={-1}
        onPointerDown={() => setLeftPress(true)}
        onPointerUp={() => setLeftPress(false)}
        onPointerLeave={() => setLeftPress(false)}
        onClick={handleLeft}
      />
      <button
        type="button"
        className="sa-hit sa-hit--right"
        tabIndex={-1}
        onPointerDown={() => setRightPress(true)}
        onPointerUp={() => setRightPress(false)}
        onPointerLeave={() => setRightPress(false)}
        onClick={handleRight}
      />
      <LogoSvg leftCls={leftCls} rightCls={rightCls} needleWobble={needleWobble} handleLeft={handleLeft} handleRight={handleRight} />
    </div>
  );
}

export default function SettingsAside() {
  const [index, setIndex] = useState(0);
  const [changing, setChanging] = useState(false);
  const [leftPress, setLeftPress] = useState(false);
  const [rightPress, setRightPress] = useState(false);
  const [rightAuto, setRightAuto] = useState(false);
  const [needleWobble, setNeedleWobble] = useState(false);
  const autoRef = useRef(null);
  const autoEnabledRef = useRef(true);

  function triggerWobble() {
    setNeedleWobble(false);
    requestAnimationFrame(() => setNeedleWobble(true));
  }

  const stepPhrase = useCallback((dir) => {
    triggerWobble();
    setChanging(true);
    setTimeout(() => {
      setIndex((i) => (i + dir + PHRASES.length) % PHRASES.length);
      setChanging(false);
    }, TRANSITION_MS);
  }, []);

  const stopAuto = useCallback(() => {
    autoEnabledRef.current = false;
    clearTimeout(autoRef.current);
    setRightAuto(false);
    setLeftPress(false);
    setRightPress(false);
  }, []);

  const scheduleAuto = useCallback(() => {
    if (!autoEnabledRef.current) return;
    clearTimeout(autoRef.current);
    autoRef.current = setTimeout(() => {
      if (!autoEnabledRef.current) return;
      setRightAuto(true);
      setTimeout(() => {
        setRightAuto(false);
        stepPhrase(1);
        scheduleAuto();
      }, TRANSITION_MS);
    }, AUTO_ADVANCE_MS);
  }, [stepPhrase]);

  useEffect(() => {
    autoEnabledRef.current = true;
    scheduleAuto();
    return () => clearTimeout(autoRef.current);
  }, [scheduleAuto]);

  useEffect(() => {
    function onKey(e) {
      if (e.key === 'ArrowLeft')  { stopAuto(); stepPhrase(-1); }
      if (e.key === 'ArrowRight') { stopAuto(); stepPhrase(1); }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [stopAuto, stepPhrase]);

  function handleLeft() { stopAuto(); stepPhrase(-1); }
  function handleRight() { stopAuto(); stepPhrase(1); }

  const leftCls  = leftPress  ? 'sa-chevron sa-chevron--press' : 'sa-chevron';
  const rightCls = rightAuto  ? 'sa-chevron sa-chevron--auto'
                 : rightPress ? 'sa-chevron sa-chevron--press'
                 :              'sa-chevron';

  return (
    <div className="settings-aside" aria-hidden="true">
      <div className="sa-brand">
        <LogoShell
          leftPress={leftPress} setLeftPress={setLeftPress}
          rightPress={rightPress} setRightPress={setRightPress}
          leftCls={leftCls} rightCls={rightCls}
          needleWobble={needleWobble} handleLeft={handleLeft} handleRight={handleRight}
        />
        <span className="sa-wordmark">quodeq</span>
        <p className="sa-phrase-wrap">
          <span className={changing ? 'sa-phrase sa-phrase--changing' : 'sa-phrase'}>
            <SafePhrase html={PHRASES[index]} />
          </span>
        </p>
      </div>
    </div>
  );
}
