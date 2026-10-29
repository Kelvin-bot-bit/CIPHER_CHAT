// Flask-JWT-Extended's cookie mode (JWT_COOKIE_CSRF_PROTECT = True, which this
// backend has enabled) uses the "double submit cookie" pattern: alongside the
// httpOnly access/refresh cookies, it sets a *readable* `csrf_access_token`
// (and `csrf_refresh_token`) cookie. The frontend must read that value and
// echo it back in an `X-CSRF-TOKEN` header on state-changing requests, or the
// backend will reject them with 401/403 even though the session cookie itself
// is valid. This is why we never need to store the JWT ourselves for HTTP
// calls — the httpOnly cookie plus this CSRF echo is the whole mechanism.

function readCookie(name) {
  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : null
}

export function getCsrfAccessToken() {
  return readCookie('csrf_access_token')
}

export function getCsrfRefreshToken() {
  return readCookie('csrf_refresh_token')
}
