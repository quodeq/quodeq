// Pure helpers for the assistant command layer: meta-command parsing,
// autocomplete matching, and welcome/pill derivation. No React, no network.
// META_COMMANDS mirrors RESERVED_COMMANDS in src/quodeq/assistant/skills.py
// and doubles as the offline fallback when the catalog fetch fails.

export const META_COMMANDS = [
  { name: 'help', description: 'Show what the assistant can do here' },
  { name: 'skills', description: 'List available skill commands' },
  // Still answered locally if typed, but hidden from the welcome list,
  // /help, and autocomplete until the Phase 2 action registry gives it
  // more than one entry. The name stays reserved server-side.
  { name: 'actions', description: 'List actions the assistant can draft', hidden: true },
  { name: 'clear', description: 'Start a new conversation' },
];

export const VISIBLE_META_COMMANDS = META_COMMANDS.filter((c) => !c.hidden);

export function parseMetaCommand(text) {
  const first = text.trim().split(/\s+/)[0];
  if (!first.startsWith('/')) return null;
  const name = first.slice(1);
  return META_COMMANDS.some((c) => c.name === name) ? name : null;
}

export function matchCommands(catalog, draft) {
  if (!draft.startsWith('/') || /\s/.test(draft)) return [];
  const prefix = draft.slice(1).toLowerCase();
  const skills = (catalog?.skills ?? []).map((s) => ({
    name: s.name, description: s.description, argumentHint: s.argumentHint || '',
  }));
  return [...VISIBLE_META_COMMANDS.map((c) => ({ ...c, argumentHint: '' })), ...skills]
    .filter((c) => c.name.startsWith(prefix));
}

function commandLines(catalog) {
  const skills = catalog?.skills ?? [];
  return [
    ...VISIBLE_META_COMMANDS.map((c) => `- \`/${c.name}\` ${c.description}`),
    ...skills.map((s) => `- \`/${s.name}${s.argumentHint ? ` ${s.argumentHint}` : ''}\` ${s.description}`),
  ].join('\n');
}

export function buildMetaResponse(kind, catalog) {
  if (kind === 'skills') {
    const skills = catalog?.skills ?? [];
    if (!skills.length) return 'No skill packs are installed.';
    return `**Skills**\n${skills.map((s) => `- \`/${s.name}${s.argumentHint ? ` ${s.argumentHint}` : ''}\` ${s.description}`).join('\n')}`;
  }
  if (kind === 'actions') {
    const actions = catalog?.actions ?? [];
    if (!actions.length) return 'No draftable actions are available.';
    return `**Actions** (drafted as preview cards, applied only after you approve)\n${actions.map((a) => `- \`${a.type}\` ${a.description}`).join('\n')}`;
  }
  return `I can explain scores, dig into findings, and draft standards for this project.\n\n**Commands**\n${commandLines(catalog)}`;
}

export function pillsForView(catalog, view) {
  if (!view) return [];
  const skills = catalog?.skills ?? [];
  // View-relevant skills lead; the rest follow so any view with context
  // offers every skill as a pill (skills appear only here, not as text).
  const matching = skills.filter((s) => (s.views ?? []).includes(view));
  const rest = skills.filter((s) => !(s.views ?? []).includes(view));
  return [...matching, ...rest]
    .slice(0, 4)
    .map((s) => ({
      label: s.name.replace(/-/g, ' ').replace(/^./, (ch) => ch.toUpperCase()),
      fill: `/${s.name} `,
      description: s.description,
    }));
}
