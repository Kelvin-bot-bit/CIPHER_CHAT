import { api } from './api'

// Converts the VAPID public key (base64url, as the backend hands it out)
// into the raw byte array pushManager.subscribe() expects.
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)))
}

export function isPushSupported() {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

export async function getPushStatus() {
  if (!isPushSupported()) return { supported: false, subscribed: false, permission: 'unsupported' }
  const registration = await navigator.serviceWorker.getRegistration('/sw.js')
  const existing = registration ? await registration.pushManager.getSubscription() : null
  return {
    supported: true,
    subscribed: Boolean(existing),
    permission: Notification.permission,
  }
}

// Registers the service worker, asks for notification permission if
// needed, subscribes with the browser's push service, and hands the
// subscription details to the backend. Each step can fail independently
// (permission denied, push service unreachable, etc.) — callers should
// wrap this in a try/catch and show a real error rather than assuming it
// always succeeds.
export async function enablePush() {
  if (!isPushSupported()) {
    throw new Error('Push notifications are not supported in this browser')
  }

  const keyRes = await api.get('/push/vapid-public-key')
  if (!keyRes.data.configured || !keyRes.data.vapid_public_key) {
    throw new Error('Push notifications are not configured on the server yet')
  }

  const registration = await navigator.serviceWorker.register('/sw.js')
  await navigator.serviceWorker.ready

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Notification permission was not granted')
  }

  let subscription = await registration.pushManager.getSubscription()
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(keyRes.data.vapid_public_key),
    })
  }

  const json = subscription.toJSON()
  await api.post('/push/subscribe', {
    endpoint: json.endpoint,
    keys: json.keys,
  })

  return true
}

export async function disablePush() {
  if (!isPushSupported()) return
  const registration = await navigator.serviceWorker.getRegistration('/sw.js')
  if (!registration) return
  const subscription = await registration.pushManager.getSubscription()
  if (!subscription) return

  const endpoint = subscription.endpoint
  await subscription.unsubscribe()
  try {
    await api.post('/push/unsubscribe', { endpoint })
  } catch {
    // The browser-side unsubscribe already succeeded, which is what
    // actually stops pushes arriving — a failure to also tell the
    // backend just leaves one harmless orphaned row it'll prune next
    // time a push to that endpoint 404s/410s.
  }
}
