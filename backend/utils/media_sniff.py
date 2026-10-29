# backend/utils/media_sniff.py
"""
Identify an uploaded photo/video from its *content*, not from what the client
claims.

A browser-supplied Content-Type (or file extension) is just a string the
uploader chose. If the server echoed it back when the file is later served,
a friend could post an HTML or SVG document labelled "video/mp4" and have it
rendered by the viewer's browser. So the type is decided here from the file's
signature, only a short allow-list is accepted, and that detected type is the
one stored and served.
"""

# Brand codes (bytes 8..12 of an ISO base-media "ftyp" box).
_QUICKTIME = {b'qt  '}
_M4V = {b'M4V ', b'M4VH', b'M4VP'}
_AVIF = {b'avif', b'avis'}
_HEIC = {b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'mif1', b'msf1'}
_AUDIO_ONLY = {b'M4A ', b'M4B ', b'M4P '}

IMAGE_TYPES = ('image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/avif', 'image/heic')
VIDEO_TYPES = ('video/mp4', 'video/quicktime', 'video/x-m4v', 'video/webm')


def sniff_media(data):
    """
    Return ``('image' | 'video', mime_type)`` for supported content, else None.
    Only the first few hundred bytes are inspected.
    """
    head = bytes(data[:512])
    if len(head) < 12:
        return None

    if head.startswith(b'\xff\xd8\xff'):
        return 'image', 'image/jpeg'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image', 'image/png'
    if head.startswith((b'GIF87a', b'GIF89a')):
        return 'image', 'image/gif'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image', 'image/webp'

    # MP4 / MOV / M4V / AVIF / HEIC all share the ISO base-media container.
    if head[4:8] == b'ftyp':
        brand = head[8:12]
        if brand in _AUDIO_ONLY:
            return None
        if brand in _AVIF:
            return 'image', 'image/avif'
        if brand in _HEIC:
            return 'image', 'image/heic'
        if brand in _QUICKTIME:
            return 'video', 'video/quicktime'
        if brand in _M4V:
            return 'video', 'video/x-m4v'
        return 'video', 'video/mp4'

    # WebM is Matroska with doctype "webm" (plain .mkv is not accepted).
    if head.startswith(b'\x1a\x45\xdf\xa3') and b'webm' in head[:64]:
        return 'video', 'video/webm'

    return None


def describe_allowed():
    return ('a JPEG, PNG, GIF, WebP or AVIF photo, or an MP4, MOV or WebM video')
