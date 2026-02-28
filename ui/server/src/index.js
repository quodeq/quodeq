import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from './app.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  const args = {
    evaluations: './evaluations',
    repoRoot: '.',
    port: 3001,
    staticDist: path.resolve(__dirname, '../../web/dist'),
    actionApi: null,
    help: false
  };

  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    const match = arg.match(/^--([^=]+)(=(.*))?$/);
    if (!match) continue;

    const key = match[1];
    const inlineValue = match[3];
    const value = inlineValue ?? next;

    switch (key) {
      case 'evaluations':
        args.evaluations = value;
        if (!inlineValue) i += 1;
        break;
      case 'repo-root':
        args.repoRoot = value;
        if (!inlineValue) i += 1;
        break;
      case 'port':
        args.port = Number(value);
        if (!inlineValue) i += 1;
        break;
      case 'static-dist':
        args.staticDist = value;
        if (!inlineValue) i += 1;
        break;
      case 'action-api':
        args.actionApi = value;
        if (!inlineValue) i += 1;
        break;
      case 'help':
        args.help = true;
        break;
      default:
        break;
    }
  }

  return args;
}

function printHelp() {
  console.log(`Usage: node ui/server/src/index.js [options]

Options:
  --evaluations <dir>  Path to evaluations directory (default: ./evaluations)
  --repo-root <dir>    Repository root for job manager (default: .)
  --port <num>         Port to listen on (default: 3001)
  --static-dist <dir>  Path to built web dist (default: ui/web/dist)
  --action-api <url>   Base URL for Python action API (default: none)
  --help               Show this help and exit
`);
}

function ensureDir(label, dirPath) {
  if (!dirPath) return { ok: false, reason: `${label} path not provided` };
  if (!fs.existsSync(dirPath)) return { ok: false, reason: `${label} not found: ${dirPath}` };
  const stat = fs.statSync(dirPath);
  if (!stat.isDirectory()) return { ok: false, reason: `${label} is not a directory: ${dirPath}` };
  return { ok: true };
}

function main() {
  const parsed = parseArgs(process.argv);

  if (parsed.help) {
    printHelp();
    process.exit(0);
  }

  const reportsRoot = path.resolve(parsed.evaluations);
  const repoRoot = path.resolve(parsed.repoRoot);
  const staticDistPath = path.resolve(parsed.staticDist);
  const port = Number.isFinite(parsed.port) ? parsed.port : 3001;
  const actionApiBase = parsed.actionApi ?? process.env.CODECOMPASS_ACTION_API ?? null;

  const distCheck = ensureDir('Static dist', staticDistPath);
  if (!distCheck.ok) {
    console.error(`[ui-server] ${distCheck.reason}`);
    process.exit(1);
  }

  const reportsCheck = ensureDir('Reports', reportsRoot);
  if (!reportsCheck.ok) {
    console.error(`[ui-server] ${reportsCheck.reason}`);
    process.exit(1);
  }

  const app = createApp({
    reportsRoot,
    repoRoot,
    staticDistPath,
    actionApiBase
  });

  const host = process.env.HOST || '127.0.0.1';

  const server = app.listen(port, host, () => {
    const actualPort = server.address().port;
    console.log(`[ui-server] listening on http://localhost:${actualPort}`);
    console.log(`[ui-server] evaluations: ${reportsRoot}`);
    console.log(`[ui-server] static dist: ${staticDistPath}`);
  });

  server.on('error', (err) => {
    console.error(`[ui-server] failed to start on ${host}:${port}`);
    if (err && err.code) {
      console.error(`[ui-server] error code: ${err.code}`);
    }
    if (err && err.message) {
      console.error(err.message);
    }
    process.exit(1);
  });
}

main();
