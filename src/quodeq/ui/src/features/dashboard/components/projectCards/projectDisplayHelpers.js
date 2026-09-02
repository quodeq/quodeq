import { LOCALE } from '../../../../strings/index.js';

// Technology and discipline names are proper nouns: a translator handed
// "React Native" would be right to leave it, and wrong to change it.
/* eslint-disable i18n/no-prose-literals */
const DISCIPLINE_LABEL = {
  frontend_nextjs: 'Next.js',
  frontend_react: 'React',
  frontend_vue: 'Vue',
  frontend_angular: 'Angular',
  frontend: 'Frontend',
  backend: 'Backend',
  backend_python: 'Python',
  backend_java: 'Java',
  backend_node: 'Node.js',
  mobile_ios: 'iOS',
  mobile_android: 'Android',
  mobile_react_native: 'React Native',
  mobile: 'Mobile',
  fullstack: 'Full Stack',
  devops: 'DevOps',
  data: 'Data',
};
/* eslint-enable i18n/no-prose-literals */

export function disciplineLabel(d) {
  if (!d) return null;
  return DISCIPLINE_LABEL[d.toLowerCase()] ?? d.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatDate(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(LOCALE, { month: 'short', day: 'numeric' });
  } catch {
    return null;
  }
}

export function formatPath(path) {
  if (!path) return null;
  const gitMatch = path.match(/[@/](github\.com|gitlab\.com|bitbucket\.org)[:/](.+?)(?:\.git)?$/);
  if (gitMatch) return `${gitMatch[1]}/${gitMatch[2]}`;
  return path;
}
