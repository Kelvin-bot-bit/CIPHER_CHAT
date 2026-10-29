import { useState } from 'react'
import BrandPanel from './BrandPanel.jsx'

// Shared shell for the login / register pages. On phones and tablets the
// brand panel covers the whole screen until the user taps its button; it
// then flips up and away to reveal the form. A small "Cipher" button at the
// top of the form flips the panel back down.
export default function AuthLayout({ ctaLabel, scrollable = false, children }) {
  const [revealed, setRevealed] = useState(false)

  return (
    <div className="flex min-h-screen flex-col bg-ink lg:flex-row">
      <BrandPanel revealed={revealed} onContinue={() => setRevealed(true)} ctaLabel={ctaLabel} />

      {/* Kept invisible (not focusable) on small screens until revealed; the
          visibility change is delayed on the way out so the form stays put
          while the panel flips back over it. */}
      <div
        className={`relative flex flex-1 items-center justify-center px-6 py-12 transition-[visibility] duration-700 motion-reduce:transition-none lg:visible ${
          scrollable ? 'overflow-y-auto' : ''
        } ${revealed ? 'visible' : 'invisible'}`}
      >
        <button
          type="button"
          onClick={() => setRevealed(false)}
          aria-label="Show Cipher introduction"
          className="absolute left-4 top-4 flex items-center gap-1.5 rounded-lg px-2 py-1.5 font-display text-lg font-semibold text-paper transition hover:bg-surface-alt lg:hidden"
        >
          Cipher
          <svg
            className="h-4 w-4 text-muted"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
        {children}
      </div>
    </div>
  )
}
