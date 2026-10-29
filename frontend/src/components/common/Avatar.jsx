const PALETTE = ['#49D6AC', '#E8A33D', '#6E9CE8', '#C77DE8', '#E5847C', '#7CC7C0']

function colorFor(seed) {
  let hash = 0
  for (let i = 0; i < (seed || '').length; i++) hash = (hash << 5) - hash + seed.charCodeAt(i)
  return PALETTE[Math.abs(hash) % PALETTE.length]
}

const STATUS_COLOR = {
  online: 'bg-signal',
  away: 'bg-amber',
  busy: 'bg-danger',
  offline: 'bg-muted',
}

export default function Avatar({ name = '?', src, size = 40, status, className = '' }) {
  const initials = name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('') || '?'

  return (
    <div className={`relative shrink-0 ${className}`} style={{ width: size, height: size }}>
      {src ? (
        <img
          src={src}
          alt=""
          width={size}
          height={size}
          className="h-full w-full rounded-full object-cover"
        />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center rounded-full font-display font-semibold text-ink"
          style={{ backgroundColor: colorFor(name), fontSize: size * 0.38 }}
        >
          {initials}
        </div>
      )}
      {status && (
        <span
          className={`absolute -bottom-0.5 -right-0.5 block rounded-full ring-2 ring-surface ${STATUS_COLOR[status] || 'bg-muted'}`}
          style={{ width: size * 0.3, height: size * 0.3 }}
          aria-label={`Status: ${status}`}
        />
      )}
    </div>
  )
}
