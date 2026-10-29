import { Component, lazy, Suspense, useEffect, useState } from 'react'

// The globe (three.js + textures) is loaded on demand so the sign-in form
// appears instantly. If WebGL or the chunk is unavailable, the original
// feature list is shown instead.
const InteractiveGlobe = lazy(() => import('./InteractiveGlobe.jsx'))

class GlobeBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch() {
    this.props.onFail?.()
  }
  render() {
    return this.state.failed ? null : this.props.children
  }
}

function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const update = () => setMatches(mq.matches)
    update()
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [query])
  return matches
}

// Phones & tablets (< lg): a full-screen intro that sits on top of the form.
// Tapping the call-to-action flips the panel up and away, revealing the form
// underneath. Desktop (lg and up): the static left-hand column, as before.
export default function BrandPanel({ revealed = false, onContinue, ctaLabel = 'Continue' }) {
  const [globeFailed, setGlobeFailed] = useState(false)
  const isDesktop = useMediaQuery('(min-width: 1024px)')

  const state = revealed
    ? 'invisible opacity-0 [transform:perspective(1200px)_translateY(-100%)_rotateX(-75deg)]'
    : 'visible opacity-100 [transform:perspective(1200px)_translateY(0)_rotateX(0deg)]'

  return (
    <div
      className={`fixed inset-0 z-40 flex origin-top flex-col justify-between gap-6 overflow-hidden border-line bg-surface px-6 pb-8 pt-10 transition-[transform,opacity,visibility] duration-700 ease-in-out motion-reduce:transition-none sm:px-10 sm:pb-10 sm:pt-12 lg:relative lg:inset-auto lg:z-auto lg:w-[42%] lg:max-w-lg lg:border-r lg:px-10 lg:py-12 lg:visible lg:opacity-100 lg:transition-none lg:[transform:none] ${state}`}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, #49D6AC 1px, transparent 0)',
          backgroundSize: '28px 28px',
        }}
      />
      <p className="relative font-display text-2xl font-semibold text-paper">Cipher</p>

      <div className="relative flex min-h-0 flex-1 flex-col gap-4">
        <p className="font-display text-3xl font-semibold leading-tight text-paper">
          Every message,
          <br />
          sealed and signed.
        </p>

        {globeFailed ? (
          <ul className="space-y-3 text-sm text-muted">
            <li className="flex items-center gap-2">
              <Dot /> RSA-2048 + AES-256-GCM envelope encryption
            </li>
            <li className="flex items-center gap-2">
              <Dot /> RSA-PSS signatures verified on every message
            </li>
            <li className="flex items-center gap-2">
              <Dot /> Per-conversation key fingerprints you can verify
            </li>
          </ul>
        ) : (
          <GlobeBoundary onFail={() => setGlobeFailed(true)}>
            <Suspense fallback={<div className="min-h-[11rem] flex-1" />}>
              <InteractiveGlobe
                paused={revealed && !isDesktop}
                onUnsupported={() => setGlobeFailed(true)}
              />
            </Suspense>
          </GlobeBoundary>
        )}
      </div>

      <div className="relative space-y-5">
        <button
          type="button"
          onClick={onContinue}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-signal px-4 py-3 text-sm font-semibold text-ink transition hover:brightness-95 sm:w-auto sm:min-w-[16rem] lg:hidden"
        >
          {ctaLabel}
          <svg
            className="h-4 w-4 animate-bounce motion-reduce:animate-none"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M6 15l6-6 6 6" />
          </svg>
        </button>
        <p className="text-xs text-muted">Cipher Chat — reference client</p>
      </div>
    </div>
  )
}

function Dot() {
  return <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
}
