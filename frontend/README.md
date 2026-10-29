# Cipher — Secure Chat Frontend

A React + Vite frontend for the Flask "secure chat" backend, matched to its
actual API contract (JWT-in-httpOnly-cookie auth with CSRF double-submit,
hybrid RSA-2048 + AES-256-GCM message encryption, RSA-PSS signatures,
real-time via Socket.IO, friends/groups/files).

## Setup

```bash
cd frontend
npm install
cp .env.example .env      # defaults are fine for local dev
npm run dev
```

This assumes the Flask backend is running on `http://127.0.0.1:5000` with
the `app.py` / `routes/auth.py` / `socket_events/presence_events.py` fixes
already applied (config selection, access-token exposure for sockets, and
the disconnect-tracking fix) — real-time features depend on those. The Vite
dev server proxies `/api` and `/socket.io` to it (see `vite.config.js`),
which keeps requests same-site so the auth cookies work without extra CORS
configuration. Override the target with `VITE_BACKEND_ORIGIN` in `.env` if
your backend runs elsewhere.

For a production build, set `VITE_API_BASE_URL` to the backend's real origin
and run `npm run build`; serve the `dist/` folder from any static host, and
set the *real* Content-Security-Policy as an HTTP response header from that
host (the CSP `<meta>` tag in `index.html` is a local-dev baseline only — it
can't restrict `frame-ancestors` or set `report-uri`).

## Security decisions worth knowing about

- **No token in localStorage/sessionStorage for HTTP requests.** The backend
  sets the JWT as an httpOnly cookie, so the frontend never holds it in JS
  for regular API calls — `axios` just sends `withCredentials: true`.
- **One deliberate exception:** the raw access token *is* kept in memory
  (`AuthContext`'s `accessToken`, never persisted to disk) because Socket.IO's
  handshake needs the literal string — httpOnly cookies can't be read by JS
  at all, so there's no other way to authenticate a socket. This is the one
  carve-out from "never expose the JWT to JS," and it's scoped as narrowly
  as possible: memory-only, cleared on logout, never localStorage.
- **CSRF double-submit.** Every mutating request echoes the readable
  `csrf_access_token` cookie back as an `X-CSRF-TOKEN` header (`src/lib/csrf.js`).
- **The decryption password lives in memory only**, cleared after 15 minutes
  idle or on refresh/logout, never written to disk.
- **Key fingerprint verification** (`FingerprintRibbon`) and **real signature
  badges** (`SecurityBadge`, reflecting the backend's actual `is_valid_signature`)
  — both described in earlier notes, unchanged.
- **File attachments are weaker than they look.** `/files/upload` and
  `/files/download` both require a `password` field, which reads as
  "password-protected like messages" — but `FileService` never actually
  uses it. Each file's AES key is randomly generated and stored in
  plaintext in the `files` table, not derived from or wrapped by the
  uploader's password/private key the way message content is. Anyone with
  file-system + DB access could decrypt any uploaded file; this is
  encryption at rest against casual access, not the same guarantee RSA-
  wrapped messages get. Not something the frontend can fix — flagging it
  here rather than implying stronger protection than exists.

## Sharing files in chat

The paperclip icon in the message composer opens `FileShareModal`, which:
sends a message first (caption defaults to `📎 filename` if left blank) to
get a `message_id`, then uploads the file linked to that message via
`/files/upload`'s `message_id` param. The resulting bubble renders a file
card (name, size, download button) by resolving the attachment through
`GET /files/message/<id>` — the chat-history endpoint has `file_url`/
`file_name` on the message row but not the file's own id, size, or MIME
type, so that's a second lazy-loaded, cached-by-message-id fetch.

The header's separate "file vault" icon still opens the original
`FileUploadModal`/`FilesPanel` — your standalone list of every file you've
uploaded, independent of any conversation. The two are intentionally
different entry points: one shares a file *with someone*, the other is
just your personal upload history.

## Real-time behavior

`SocketContext` connects once a session password unlocks the app (via the
access token described above) and drives: instant message delivery, typing
indicators, and online/offline presence. A slower background poll (~20s)
still runs alongside it, because the backend only ever emits a `new_message`
socket event — edits, deletes, and reactions from *other* participants have
no matching broadcast, so those only show up via that poll, not instantly,
for anyone who isn't the one making the change.

## Compliance with the full requirements doc

Built in this pass: message edit/delete/reply-compose, emoji reactions,
block/unblock, group member management (add/remove/promote/demote/leave/
delete — admin-gated), profile view/edit + activity stats, light/dark theme
toggle, file upload progress/preview/drag-and-drop, client-side search
within currently-loaded messages, chat-scoped file sharing, and a full
notification system (bell + badge + dropdown, real-time push, read/unread,
dismiss — see below).

### Notifications — required two backend changes

This needed backend work beyond the frontend, both included in this drop:

- **`routes/notifications.py` (new file) + registering it in `app.py`.**
  `models/notification.py` and `services/notification_service.py` were
  already fully built — friend requests, new messages, and group invites
  all already call `NotificationService.create_notification()` — but no
  route file exposed any of it as an API, so there was nothing for the
  frontend to call.
- **`services/notification_service.py`**: `send_realtime_notification()`
  used the bare `emit()` imported from `flask_socketio`, but it's invoked
  from plain HTTP routes (friend requests, messages, group invites), not
  from inside a `@socketio.on` handler. Flask-SocketIO's bare `emit()` only
  works within an active socket event's request context; called from an
  HTTP view it silently no-ops. Fixed to use `socketio.emit()` (the app's
  actual instance), which is what Flask-SocketIO's own docs specify for
  triggering an event from outside a socket handler.

With both fixed: `NotificationBell` (top of the sidebar) shows a live
unread-count badge, a dropdown lists recent notifications with sender
avatars, new ones arrive via the same `notification` socket event the
backend already emits (no polling needed), and read/unread state and
dismissal are backed by the new routes.

**Deliberately not built, with reasons** (building fake UI against
unsupported endpoints seemed worse than flagging the gap):

- **Password reset** — `/auth/forgot-password` and `/auth/reset-password`
  are stubs with no real email or token verification. A frontend flow
  against them would look functional but do nothing.
- **Message read/delivered ticks** — `MessageStatus` is tracked in the DB,
  but `MessageService.decrypt_messages()` (the function backing chat
  history) never includes it in the response. No data to render.
- **Reply preview in history** — sending supports `reply_to_message_id`,
  but the chat-history endpoint doesn't echo it back, so a past reply can't
  be visually linked to its parent after the fact. Composing a reply still
  works; you just can't see *what* a historical message was replying to.
- **Voice messages** — real scope (MediaRecorder capture, playback UI,
  format handling) beyond what fit in this pass.
- **"Remember me" / logout-all-devices** — no backend concept to hook into
  (fixed cookie expiry, single-session logout only).
- **Forward** — model has `is_forwarded`/`original_sender_id` fields but no
  endpoint exposes forwarding.

## Project layout

```
src/
  lib/          axios client, CSRF helper, socket wrapper
  context/      AuthContext, SocketContext, NotificationContext, ThemeContext, ToastContext
  components/
    auth/       password strength meter
    layout/     Sidebar, BrandPanel
    chat/       ChatList, ChatWindow, MessageBubble/Input, FingerprintRibbon, TypingIndicator, FileShareModal
    friends/    FriendsPanel (list / requests / search / blocked)
    groups/     GroupsPanel, CreateGroupModal, GroupDetailsModal
    files/      FilesPanel, FileUploadModal
    profile/    ProfileModal
    common/     Avatar, Modal, Spinner, SecurityBadge, SessionUnlock
  pages/        LoginPage, RegisterPage, ChatPage
  utils/        validators, fingerprint hashing, time formatting
```

## Known gaps / next steps

- Per-chat unread counts aren't shown — `/messages/unread` only returns
  aggregate totals, not a breakdown per conversation.
- Theme toggle overrides the surface/text/border tokens via an ancestor CSS
  selector (`html.theme-light .bg-ink { ... }`) rather than a full Tailwind
  CSS-variable refactor — covers everything that matters for readability,
  but isn't a from-scratch design-token system for both themes.
- No pagination-on-scroll yet (message history is capped to the most recent
  60 per chat).
