// API client for the verifier backend. Endpoints come from Plan 3 Task 5.

export async function listVerifications(evalId) {
  const resp = await fetch(`/api/evaluations/${evalId}/verifications`);
  if (!resp.ok) throw new Error(`listVerifications: ${resp.status}`);
  return resp.json();
}

export async function getVerification(evalId, verificationId) {
  const resp = await fetch(
    `/api/evaluations/${evalId}/verifications/${verificationId}`
  );
  if (!resp.ok) throw new Error(`getVerification: ${resp.status}`);
  return resp.json();
}

export async function verifyFinding(evalId, dimension, findingId) {
  const resp = await fetch(
    `/api/evaluations/${evalId}/verify/${dimension}/${findingId}`,
    { method: "POST" }
  );
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `verifyFinding: ${resp.status}`);
  }
  return resp.json();
}
