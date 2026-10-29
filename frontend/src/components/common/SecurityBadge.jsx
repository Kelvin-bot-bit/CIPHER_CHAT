// Renders the actual result of the backend's RSA-PSS signature check
// (`is_valid_signature` from CryptoService.decrypt_message) as a small seal.
// Solid mint lock = signature verified against the sender's public key.
// Dashed amber lock = signature missing/invalid — shown, not hidden, because
// silently swallowing a failed verification defeats the point of signing.
export default function SecurityBadge({ verified, size = 13 }) {
  return (
    <span
      className={`inline-flex animate-seal items-center gap-1 ${verified ? 'text-signal' : 'text-amber'}`}
      title={verified ? 'Signature verified' : 'Signature could not be verified'}
    >
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect
          x="5" y="11" width="14" height="9" rx="2"
          stroke="currentColor" strokeWidth="2"
          strokeDasharray={verified ? '0' : '3 2'}
        />
        {verified ? (
          <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        ) : (
          <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeDasharray="2 2" />
        )}
      </svg>
    </span>
  )
}
