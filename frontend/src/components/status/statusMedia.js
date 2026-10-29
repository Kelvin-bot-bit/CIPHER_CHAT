import { extractErrorMessage } from '../../lib/api'

// Keep these in step with the backend (services/status_service.py).
export const MAX_IMAGE_MB = 15
export const MAX_VIDEO_MB = 50
export const MAX_VIDEO_SECONDS = 60

// What the file picker offers. The server decides the real type from the file's
// content, so this is only a convenience filter.
export const MEDIA_ACCEPT =
  'image/jpeg,image/png,image/gif,image/webp,image/avif,video/mp4,video/quicktime,video/webm,video/x-m4v,.mp4,.m4v,.mov,.webm'

const VIDEO_EXT = new Set(['mp4', 'm4v', 'mov', 'webm'])
const IMAGE_EXT = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'avif'])

/** 'image' | 'video' | null, from the MIME type or (when the browser leaves it blank, e.g. .mov) the extension. */
export function kindOf(file) {
  if (!file) return null
  if (file.type?.startsWith('image/')) return 'image'
  if (file.type?.startsWith('video/')) return 'video'
  const ext = file.name?.split('.').pop()?.toLowerCase()
  if (VIDEO_EXT.has(ext)) return 'video'
  if (IMAGE_EXT.has(ext)) return 'image'
  return null
}

export function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return ''
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function formatSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * Reads a video's length and dimensions without uploading it, so an over-long
 * or unplayable clip is refused straight away instead of after a long upload.
 * Rejects with Error('unreadable' | 'no-video' | 'timeout').
 */
export function probeVideo(file, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    video.preload = 'metadata'
    video.muted = true
    let finished = false
    const timer = setTimeout(() => finish(reject, new Error('timeout')), timeoutMs)

    function finish(fn, value) {
      if (finished) return
      finished = true
      clearTimeout(timer)
      video.onloadedmetadata = video.onerror = video.ontimeupdate = null
      video.removeAttribute('src')
      video.load()
      URL.revokeObjectURL(url)
      fn(value)
    }

    const done = () => {
      if (!video.videoWidth || !video.videoHeight) return finish(reject, new Error('no-video'))
      finish(resolve, { duration: video.duration, width: video.videoWidth, height: video.videoHeight })
    }

    video.onloadedmetadata = () => {
      // Recorders (MediaRecorder/WebM) often report Infinity until the end has been seen.
      if (video.duration === Infinity) {
        video.ontimeupdate = () => {
          video.ontimeupdate = null
          done()
        }
        video.currentTime = 1e101
        return
      }
      done()
    }
    video.onerror = () => finish(reject, new Error('unreadable'))
    video.src = url
  })
}

/**
 * Error text from a request made with responseType: 'blob'. In that mode the
 * server's JSON error arrives as a Blob, which extractErrorMessage can't read.
 */
export async function blobErrorMessage(error, fallback) {
  const data = error?.response?.data
  if (typeof Blob !== 'undefined' && data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      if (parsed?.error) return parsed.error
    } catch {
      /* not JSON */
    }
    return fallback
  }
  return extractErrorMessage(error, fallback)
}
