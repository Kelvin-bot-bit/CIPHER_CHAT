// Mirrors backend/utils/validators.py so the UI can give instant feedback,
// but the backend re-validates everything server-side regardless — these
// are UX conveniences only, never the security boundary.

export function validateEmail(email) {
  return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email)
}

export function validateUsername(username) {
  if (!username || username.length < 3) return 'Username must be at least 3 characters'
  if (username.length > 50) return 'Username must be less than 50 characters'
  if (!/^[a-zA-Z0-9_]+$/.test(username)) return 'Only letters, numbers, and underscores'
  return null
}

const PASSWORD_RULES = [
  { test: (p) => p.length >= 8, label: 'At least 8 characters' },
  { test: (p) => /[A-Z]/.test(p), label: 'One uppercase letter' },
  { test: (p) => /[a-z]/.test(p), label: 'One lowercase letter' },
  { test: (p) => /\d/.test(p), label: 'One number' },
  { test: (p) => /[!@#$%^&*(),.?":{}|<>]/.test(p), label: 'One special character' },
]

export function passwordRuleStatus(password) {
  return PASSWORD_RULES.map((rule) => ({ label: rule.label, met: rule.test(password || '') }))
}

export function isPasswordValid(password) {
  return PASSWORD_RULES.every((rule) => rule.test(password || ''))
}
