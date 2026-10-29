import { passwordRuleStatus } from '../../utils/validators'

export default function PasswordStrengthMeter({ password }) {
  const rules = passwordRuleStatus(password)
  const metCount = rules.filter((r) => r.met).length
  const pct = (metCount / rules.length) * 100
  const barColor = metCount <= 2 ? 'bg-danger' : metCount <= 4 ? 'bg-amber' : 'bg-signal'

  return (
    <div className="space-y-2">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-alt">
        <div className={`h-full transition-all duration-300 ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <ul className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {rules.map((rule) => (
          <li key={rule.label} className={`flex items-center gap-1.5 ${rule.met ? 'text-signal' : 'text-muted'}`}>
            <span className={`h-1 w-1 rounded-full ${rule.met ? 'bg-signal' : 'bg-muted'}`} />
            {rule.label}
          </li>
        ))}
      </ul>
    </div>
  )
}
