import fs from 'node:fs';
import path from 'node:path';
import { Router } from 'express';

export function createPluginsRouter({ evaluatorsRoot }) {
  const router = Router();

  router.get('/plugins', (_req, res) => {
    try {
      if (!fs.existsSync(evaluatorsRoot)) {
        res.json([]);
        return;
      }

      const plugins = [];
      const entries = fs.readdirSync(evaluatorsRoot, { withFileTypes: true });

      for (const entry of entries) {
        if (!entry.isDirectory() || entry.name.startsWith('_')) continue;

        const pluginFile = path.join(evaluatorsRoot, entry.name, 'plugin.json');
        const dimsFile = path.join(evaluatorsRoot, entry.name, 'dimensions.json');

        if (!fs.existsSync(pluginFile)) continue;

        try {
          const plugin = JSON.parse(fs.readFileSync(pluginFile, 'utf-8'));
          const dimensions = fs.existsSync(dimsFile)
            ? JSON.parse(fs.readFileSync(dimsFile, 'utf-8'))
            : { applies: [] };

          plugins.push({
            id: plugin.id,
            name: plugin.name,
            extensions: plugin.detects?.extensions ?? [],
            dimensions: dimensions.applies.map((d) => ({
              id: d.id,
              weight: d.weight,
              iso_25010: d.iso_25010 ?? null,
            })),
          });
        } catch {
          // skip malformed plugins
        }
      }

      res.json(plugins);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  return router;
}
