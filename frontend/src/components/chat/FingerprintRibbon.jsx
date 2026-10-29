import { useEffect, useState } from 'react'
import { computeFingerprint, getVerifiedFingerprints, setFingerprintVerified } from '../../utils/fingerprint'

// The one signature element of this design: a thin, always-visible strip
// under every conversation header showing a hash of the other party's real
// RSA public key (the same key the backend uses for RSA-OAEP/PSS). This is
// the browser equivalent of Signal's "safety number" — comparing it over a
// separate channel is how two people actually detect a key substitution
// (MITM) attack, which message-level encryption alone can't reveal.
export default function FingerprintRibbon({ peerId, publicKeyPem }) {
  const [fingerprint, setFingerprint] = useState(null)
  const [verified, setVerified] = useState(() => Boolean(getVerifiedFingerprints()[peerId]))

  useEffect(() => {
    let cancelled = false
    computeFingerprint(publicKeyPem).then((fp) => {
      if (!cancelled) setFingerprint(fp)
    })
    setVerified(Boolean(getVerifiedFingerprints()[peerId]))
    return () => {
      cancelled = true
    }
  }, [publicKeyPem, peerId])

  if (!publicKeyPem) return null

  const toggle = () => {
    const next = !verified
    setVerified(next)
    setFingerprintVerified(peerId, next)
  }

  return (
    <div className="flex items-center gap-2 border-b border-line bg-surface-alt/60 px-4 py-1.5 text-xs">
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${verified ? 'bg-signal' : 'bg-amber animate-pulseDot'}`} />
      <span className="shrink-0 text-muted">Key fingerprint</span>
      <span className="truncate font-mono tracking-tight text-paper/80">{fingerprint || '—'}</span>
      <button
        onClick={toggle}
        className={`ml-auto shrink-0 rounded-full border px-2 py-0.5 font-medium transition-colors
          ${verified ? 'border-signal/40 text-signal hover:bg-signal-dim' : 'border-amber/40 text-amber hover:bg-amber-dim'}`}
      >
        {verified ? 'Verified' : 'Mark verified'}
      </button>
    </div>
  )
}
