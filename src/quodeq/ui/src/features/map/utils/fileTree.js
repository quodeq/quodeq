function createNode(name, path, isFile) {
  return {
    name, path, isFile,
    violations: 0, compliance: 0,
    severity: { critical: 0, major: 0, minor: 0 },
    dimensions: {},
    complianceRate: 0,
    children: [],
    items: [],
  };
}

function ensurePath(root, filePath) {
  const parts = filePath.split('/').filter(Boolean);
  let current = root;
  let builtPath = '';
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    builtPath += (builtPath ? '/' : '') + part;
    const isFile = i === parts.length - 1;
    let child = current.children.find((c) => c.name === part);
    if (!child) {
      child = createNode(part, builtPath, isFile);
      current.children.push(child);
    }
    current = child;
  }
  return current;
}

function aggregateUp(node) {
  if (node.children.length === 0) {
    const total = node.violations + node.compliance;
    node.complianceRate = total > 0 ? node.compliance / total : 0;
    return;
  }
  for (const child of node.children) {
    aggregateUp(child);
    node.violations += child.violations;
    node.compliance += child.compliance;
    node.severity.critical += child.severity.critical;
    node.severity.major += child.severity.major;
    node.severity.minor += child.severity.minor;
    for (const [dim, counts] of Object.entries(child.dimensions)) {
      if (!node.dimensions[dim]) node.dimensions[dim] = { violations: 0, compliance: 0 };
      node.dimensions[dim].violations += counts.violations;
      node.dimensions[dim].compliance += counts.compliance;
    }
    node.items.push(...child.items);
  }
  const total = node.violations + node.compliance;
  node.complianceRate = total > 0 ? node.compliance / total : 0;
  node.children.sort((a, b) => b.violations - a.violations);
}

export function buildFileTree(dimensions) {
  const root = createNode('/', '', false);
  for (const dim of dimensions) {
    const dimName = dim.dimension || 'Unknown';
    for (const v of dim.violations || []) {
      const filePath = v.file || '(unknown)';
      const node = ensurePath(root, filePath);
      node.violations++;
      const sev = v.severity || 'minor';
      if (node.severity[sev] !== undefined) node.severity[sev]++;
      if (!node.dimensions[dimName]) node.dimensions[dimName] = { violations: 0, compliance: 0 };
      node.dimensions[dimName].violations++;
      node.items.push({ ...v, dimension: dimName, type: 'violation' });
    }
    for (const c of dim.compliance || []) {
      const filePath = c.file || '(unknown)';
      const node = ensurePath(root, filePath);
      node.compliance++;
      if (!node.dimensions[dimName]) node.dimensions[dimName] = { violations: 0, compliance: 0 };
      node.dimensions[dimName].compliance++;
      node.items.push({ ...c, dimension: dimName, type: 'compliance' });
    }
  }
  aggregateUp(root);
  return root;
}
