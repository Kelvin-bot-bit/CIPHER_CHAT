// public/sw.js
//
// Minimal service worker whose only job is Web Push: show a system
// notification when a push arrives (which happens even if no tab of this
// app is open — that's the whole point), and focus/open the app when the
// notification is clicked. Not a caching/offline service worker — nothing
// here intercepts fetch() or caches assets, on purpose, to avoid the
// classic "stale app after a deploy" problem that comes with an
// aggressive caching SW. If offline support is wanted later, add a
// separate `install`/`fetch` caching strategy — don't bolt it onto this
// file without thinking through cache invalidation on deploy.

self.addEventListener('push', (event) => {
  let payload = { title: 'Cipher', body: 'You have a new notification', data: {} }
  try {
    if (event.data) payload = { ...payload, ...event.data.json() }
  } catch {
    // Non-JSON push payload — fall back to the default above rather than
    // failing to show anything at all.
  }

  const options = {
    body: payload.body,
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: payload.data || {},
    tag: payload.data?.notification_type || 'cipher-notification',
  }

  event.waitUntil(self.registration.showNotification(payload.title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  event.waitUntil(
    (async () => {
      const clientsList = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      const existing = clientsList.find((c) => 'focus' in c)
      if (existing) {
        existing.focus()
        return
      }
      await self.clients.openWindow('/')
    })(),
  )
})
