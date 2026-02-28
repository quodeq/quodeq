export function scoreToGrade(scoreText) {
  if (!scoreText) return null;
  const match = String(scoreText).match(/(\d+(?:\.\d+)?)/);
  if (!match) return null;
  const n = parseFloat(match[1]);
  if (n >= 9) return 'Exemplary';
  if (n >= 7) return 'Good';
  if (n >= 5) return 'Adequate';
  if (n >= 3) return 'Poor';
  return 'Critical';
}
