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

function collapseSingleChildren(node) {
  // Recursively collapse chains of single-child folders into one node
  // e.g. java/ -> app/ -> src/ becomes java/app/src/
  for (let i = 0; i < node.children.length; i++) {
    let child = node.children[i];
    while (!child.isFile && child.children.length === 1 && !child.children[0].isFile) {
      const grandchild = child.children[0];
      grandchild.name = child.name + '/' + grandchild.name;
      child = grandchild;
    }
    node.children[i] = child;
    if (child.children.length > 0) {
      collapseSingleChildren(child);
    }
  }
}

/** Convert a tree node into a file object, optionally filtered by severity.
 *  severity: null = all violations, 'critical'|'major'|'minor' = filtered, 'all' = violations + compliance */
export function treeNodeToFileObj(node, { severity } = {}) {
  let violations = node.items.filter((i) => i.type === 'violation');
  let compliance = node.items.filter((i) => i.type === 'compliance');
  if (severity && severity !== 'all') {
    violations = violations.filter((v) => (v.severity || 'minor') === severity);
    compliance = []; // severity filter shows only violations
  }
  const bySev = { critical: [], major: [], minor: [], unknown: [] };
  for (const v of violations) {
    const sev = v.severity || 'minor';
    (bySev[sev] || bySev.unknown).push(v);
  }
  const dims = new Set(violations.map((v) => v.dimension).filter(Boolean));
  return {
    file: node.path,
    total: violations.length,
    critical: bySev.critical.length,
    major: bySev.major.length,
    minor: bySev.minor.length,
    unknown: bySev.unknown.length,
    dimensions: Array.from(dims).sort(),
    dimensionsCount: dims.size,
    principlesCount: new Set(violations.map((v) => v.principle).filter(Boolean)).size,
    violationsBySeverity: bySev,
    compliance,
  };
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
  collapseSingleChildren(root);
  return root;
}
