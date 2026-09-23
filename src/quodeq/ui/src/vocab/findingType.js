// Mirror of src/quodeq/core/types/finding_type.py:FindingType. The API sends
// findings already split into violations/compliance buckets, so the UI spells
// these as its own row kinds (explorer lists, map file items) and as the
// "compliance only" filter value.
export const FINDING_TYPE = Object.freeze({ VIOLATION: 'violation', COMPLIANCE: 'compliance' });
