import { Router } from 'express';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

export function createBrowseRouter() {
  const router = Router();

  router.get('/browse', (req, res) => {
    const requestedPath = req.query.path || os.homedir();

    try {
      const resolvedPath = path.resolve(requestedPath);

      if (!fs.existsSync(resolvedPath)) {
        return res.status(404).json({ error: 'Path not found', path: resolvedPath });
      }

      const stat = fs.statSync(resolvedPath);
      if (!stat.isDirectory()) {
        return res.status(400).json({ error: 'Path is not a directory', path: resolvedPath });
      }

      const entries = fs.readdirSync(resolvedPath, { withFileTypes: true });
      const directories = entries
        .filter(entry => {
          if (entry.name.startsWith('.')) return false;
          if (entry.isDirectory()) {
            try {
              fs.accessSync(path.join(resolvedPath, entry.name), fs.constants.R_OK);
              return true;
            } catch {
              return false;
            }
          }
          return false;
        })
        .map(entry => ({
          name: entry.name,
          path: path.join(resolvedPath, entry.name),
          isGitRepo: fs.existsSync(path.join(resolvedPath, entry.name, '.git'))
        }))
        .sort((a, b) => a.name.localeCompare(b.name));

      const parentPath = path.dirname(resolvedPath);

      res.json({
        current: resolvedPath,
        parent: parentPath !== resolvedPath ? parentPath : null,
        directories,
        isGitRepo: fs.existsSync(path.join(resolvedPath, '.git'))
      });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  return router;
}
