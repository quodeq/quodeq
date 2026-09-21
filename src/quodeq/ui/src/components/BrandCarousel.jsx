import { useState, useEffect, useRef, useCallback } from 'react';
import { BRAND_NAME } from '../strings/brand.js';
import {
  LOGO_VIEWBOX,
  LOGO_PATH_TRANSFORM,
  LOGO_LEFT_CHEVRON_D,
  LOGO_RIGHT_CHEVRON_D,
  LOGO_Q_D,
  LOGO_NEEDLE_LIGHT_D,
  LOGO_NEEDLE_DARK_D,
  LogoNeedleMask,
} from './brandLogoArt.jsx';

// Unique per component: the sidebar logo draws the same mark with its own
// mask, and two elements sharing a DOM id would collide when both are mounted.
const NEEDLE_MASK_ID = 'sa-needle-mask';

const PHRASES = [
  'evaluate <b>local folders</b> or <b>remote git repositories</b>, no cloning needed',
  'target a <b>subfolder</b> to focus analysis on a specific module or service',
  'run evaluations over time and <b>track quality trends</b> across runs',
  'each finding includes a <b>fix plan</b>, a concrete path to resolve the issue',
  'violations explain <b>what went wrong</b>, why it matters, and <b>how to fix it</b>',
  'findings are mapped to <b>CWE</b>, the industry standard for software weaknesses',
  'dimensions follow <b>ISO 25010</b>, the international standard for software quality',
  'quality covers <b>reliability</b>, <b>security</b>, <b>maintainability</b>, <b>performance</b>, and more',
  'compare <b>accumulated scores</b> across all runs to see overall project health',
  'use <b>parallel subagents</b> to speed up evaluations across multiple dimensions',
  'the <b>compliance ratio</b> shows how many rules pass for every violation found',
  'click any <b>dimension card</b> to explore violations, files, and principles in detail',
  'copy a <b>fix plan</b> to your clipboard and paste it into your IDE or AI assistant',
  'choose between <b>fast</b>, <b>balanced</b>, or <b>thorough</b> analysis modes',
  'switch <b>themes</b>, from Daruma to Neo, Deckard to Galadriel',
  'the <b>score history</b> chart shows how your codebase quality evolves over time',
  'violations are ranked by <b>severity</b>: critical, major, and minor',
  'every principle is graded and mapped to a <b>quality dimension</b>',
  'use <b>Clean scan</b> when you want every file re-analyzed; otherwise Quodeq carries unchanged files forward automatically',
  'run analysis with <b>local Ollama</b> models for free, private code review on your own machine',
  'the <b>code map</b> visualises file size and issue density so you can spot hotspots at a glance',
  'every finding gets a <b>severity</b>, an explanation, and pointers to the exact code that triggered it',
  'dismiss <b>false positives</b> in one click and they disappear from future runs too',
  'group <b>sub-projects</b> from the same repo to compare quality across services or modules',
  'the <b>Q&#xB2; formula</b> rewards strong compliance and never lets minor issues swamp critical ones',
  'write <b>custom standards</b> in JSON when the built-in dimensions are not enough',
  'ask any <b>AI assistant</b> to draft a custom standard for you, then drop the JSON file into Quodeq',
  'enable <b>Clean Architecture</b> and <b>DDD</b> dimensions when you want architectural review, not just quality',
  'the <b>severity grade floor</b> stops compliance from hiding genuinely critical issues',
  'click a <b>file</b> in the violations grid to read the offending lines in context',
  'every run is saved, so you can <b>look back</b> and see when a regression first appeared',
];

const AUTO_ADVANCE_MS = 3500;
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
    <svg className="sa-logo" viewBox={LOGO_VIEWBOX} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <LogoNeedleMask id={NEEDLE_MASK_ID} />
      </defs>
      <path
        className={leftCls}
        d={LOGO_LEFT_CHEVRON_D}
        transform={LOGO_PATH_TRANSFORM}
        onClick={handleLeft}
        style={{ cursor: 'pointer' }}
      />
      <path
        className={rightCls}
        d={LOGO_RIGHT_CHEVRON_D}
        transform={LOGO_PATH_TRANSFORM}
        onClick={handleRight}
        style={{ cursor: 'pointer' }}
      />
      <path
        d={LOGO_Q_D}
        transform={LOGO_PATH_TRANSFORM}
        fill="var(--logo-q)"
        fillRule="evenodd"
      />
      <g
        className={needleWobble ? 'sa-needle sa-needle--wobble' : 'sa-needle'}
        mask={`url(#${NEEDLE_MASK_ID})`}
      >
        <path d={LOGO_NEEDLE_LIGHT_D} fill="var(--logo-needle)" />
        <path d={LOGO_NEEDLE_DARK_D} fill="var(--logo-needle-dark)" />
      </g>
    </svg>
  );
}

function LogoShell({ press, classes, needleWobble, handlers }) {
  const { setLeft: setLeftPress, setRight: setRightPress } = press;
  const { left: leftCls, right: rightCls } = classes;
  const { left: handleLeft, right: handleRight } = handlers;
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

function useKeyNav(stopAuto, stepPhrase) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'ArrowLeft') { stopAuto(); stepPhrase(-1); }
      if (e.key === 'ArrowRight') { stopAuto(); stepPhrase(1); }
    }
    // Browser-only: keyboard navigation for rotating phrases
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [stopAuto, stepPhrase]);
}

function useAutoAdvance(stepPhrase, setRightAuto, setLeftPress, setRightPress) {
  const autoRef = useRef(null);
  const innerAutoRef = useRef(null);
  const autoEnabledRef = useRef(true);

  const stopAuto = useCallback(() => {
    autoEnabledRef.current = false;
    clearTimeout(autoRef.current);
    clearTimeout(innerAutoRef.current);
    setRightAuto(false);
    setLeftPress(false);
    setRightPress(false);
  }, [setRightAuto, setLeftPress, setRightPress]);

  const scheduleAuto = useCallback(() => {
    if (!autoEnabledRef.current) return;
    clearTimeout(autoRef.current);
    autoRef.current = setTimeout(() => {
      if (!autoEnabledRef.current) return;
      setRightAuto(true);
      innerAutoRef.current = setTimeout(() => {
        if (!autoEnabledRef.current) return;
        setRightAuto(false); stepPhrase(1); scheduleAuto();
      }, TRANSITION_MS);
    }, AUTO_ADVANCE_MS);
  }, [stepPhrase, setRightAuto]);

  useEffect(() => {
    autoEnabledRef.current = true;
    scheduleAuto();
    return () => {
      autoEnabledRef.current = false;
      clearTimeout(autoRef.current);
      clearTimeout(innerAutoRef.current);
    };
  }, [scheduleAuto]);

  return { stopAuto, scheduleAuto };
}

function useCarousel() {
  const [index, setIndex] = useState(() => Math.floor(Math.random() * PHRASES.length));
  const [changing, setChanging] = useState(false);
  const [leftPress, setLeftPress] = useState(false);
  const [rightPress, setRightPress] = useState(false);
  const [rightAuto, setRightAuto] = useState(false);
  const [needleWobble, setNeedleWobble] = useState(false);

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

  const { stopAuto } = useAutoAdvance(stepPhrase, setRightAuto, setLeftPress, setRightPress);
  useKeyNav(stopAuto, stepPhrase);

  const handleLeft = () => { stopAuto(); stepPhrase(-1); };
  const handleRight = () => { stopAuto(); stepPhrase(1); };
  const leftCls = leftPress ? 'sa-chevron sa-chevron--press' : 'sa-chevron';
  const rightCls = rightAuto ? 'sa-chevron sa-chevron--auto' : rightPress ? 'sa-chevron sa-chevron--press' : 'sa-chevron';

  return { index, changing, leftPress, setLeftPress, rightPress, setRightPress, needleWobble, leftCls, rightCls, handleLeft, handleRight };
}

export default function BrandCarousel() {
  const c = useCarousel();

  return (
    <div className="brand-carousel" aria-hidden="true">
      <div className="sa-brand">
        <LogoShell
          press={{ left: c.leftPress, setLeft: c.setLeftPress, right: c.rightPress, setRight: c.setRightPress }}
          classes={{ left: c.leftCls, right: c.rightCls }}
          needleWobble={c.needleWobble}
          handlers={{ left: c.handleLeft, right: c.handleRight }}
        />
        <span className="sa-wordmark">{BRAND_NAME}</span>
        <p className="sa-phrase-wrap">
          <span className={c.changing ? 'sa-phrase sa-phrase--changing' : 'sa-phrase'}>
            <SafePhrase html={PHRASES[c.index]} />
          </span>
        </p>
      </div>
    </div>
  );
}
