import { useMemo } from 'react';
import { LevelInfoPanel } from './galaxyViewInfo.jsx';
import { computeLevelInfo } from './packLevelInfo.js';

export default function PackInfoPanel({ focusNode, root, onFileClick }) {
  const levelInfo = useMemo(() => computeLevelInfo(focusNode, root, onFileClick), [focusNode, root, onFileClick]);
  return <LevelInfoPanel levelInfo={levelInfo} />;
}
