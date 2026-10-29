export default function TypingIndicator({ names }) {
  if (!names || names.length === 0) return null
  const label = names.length === 1 ? `${names[0]} is typing` : `${names.slice(0, 2).join(', ')} are typing`

  return (
    <div className="flex items-center gap-2 px-4 py-1 text-xs text-muted">
      <span className="flex gap-0.5">
        <span className="h-1.5 w-1.5 animate-pulseDot rounded-full bg-signal [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-pulseDot rounded-full bg-signal [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-pulseDot rounded-full bg-signal [animation-delay:300ms]" />
      </span>
      {label}
    </div>
  )
}
