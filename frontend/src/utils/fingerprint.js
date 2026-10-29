// Computes a short, human-verifiable fingerprint of an RSA public key (PEM),
// the same way Signal/WhatsApp-style "safety numbers" work: hash the key,
// show it in short groups, let two people compare it out of band. This runs
// entirely in the browser via SubtleCrypto — the PEM is public data, so no
// secret ever touches this function.
export async function computeFingerprint(publicKeyPem) {
  if (!publicKeyPem) return null
  const bytes = new TextEncoder().encode(publicKeyPem.trim())
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
  // Group into 4-char blocks, take 6 blocks (24 hex chars / 96 bits) —
  // enough entropy for a visual/verbal comparison without a wall of text.
  return hex
    .slice(0, 24)
    .toUpperCase()
    .match(/.{1,4}/g)
    .join(' ')
}

const VERIFIED_KEY = 'cipher.verifiedFingerprints'

export function getVerifiedFingerprints() {
  try {
    return JSON.parse(localStorage.getItem(VERIFIED_KEY) || '{}')
  } catch {
    return {}
  }
}

// Verification marks are a local trust decision (like Signal's "mark as
// verified") — they never leave the device and never touch the password
// or private key, so storing them in localStorage carries no secret-
// exposure risk.
export function setFingerprintVerified(peerId, verified) {
  const current = getVerifiedFingerprints()
  if (verified) {
    current[peerId] = true
  } else {
    delete current[peerId]
  }
  localStorage.setItem(VERIFIED_KEY, JSON.stringify(current))
}
