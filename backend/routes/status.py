# backend/routes/status.py
from flask import Blueprint, Response, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.status_service import StatusService
import logging
import re

status_bp = Blueprint('status', __name__)
logger = logging.getLogger(__name__)


@status_bp.route('/', methods=['POST'])
@jwt_required()
def create_status():
    """
    Post a status update (text, a photo, or a short video, with an
    optional caption), visible to friends for 24 hours.
    ---
    tags:
      - Status
    parameters:
      - name: caption
        in: formData
        type: string
      - name: media
        in: formData
        type: file
        description: A photo (JPEG/PNG/GIF/WebP/AVIF, up to 15MB) or video (MP4/MOV/WebM, up to 50MB). The legacy field name "image" is still accepted.
      - name: password
        in: formData
        required: true
        type: string
        description: Needed to sign the post with the poster's private key
      - name: lifetime_hours
        in: formData
        type: integer
        default: 24
      - name: background_color
        in: formData
        type: string
        description: Hex color for a text-only post's background
    responses:
      200:
        description: Status posted
    """
    try:
        user_id = int(get_jwt_identity())

        caption = request.form.get('caption', '')
        password = request.form.get('password')
        lifetime_hours = request.form.get('lifetime_hours', 24, type=int)
        background_color = request.form.get('background_color')

        if not password:
            return jsonify({'error': 'Password is required'}), 400

        media_data = None
        media_filename = None
        media_mime_type = None
        upload = request.files.get('media') or request.files.get('image')
        if upload and upload.filename:
            media_data = upload.read()
            media_filename = upload.filename
            media_mime_type = upload.content_type  # informational only; the real type is detected

        result = StatusService.create_status(
            user_id=user_id,
            password=password,
            caption=caption,
            media_data=media_data,
            media_filename=media_filename,
            media_mime_type=media_mime_type,
            lifetime_hours=lifetime_hours,
            background_color=background_color
        )

        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Create status error: {str(e)}")
        return jsonify({'error': 'Failed to post status'}), 500


@status_bp.route('/feed', methods=['GET'])
@jwt_required()
def get_feed():
    """
    Active statuses from the current user and their friends, grouped by
    poster.
    ---
    tags:
      - Status
    responses:
      200:
        description: Status feed retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        result = StatusService.get_feed(user_id)
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get status feed error: {str(e)}")
        return jsonify({'error': 'Failed to get status feed'}), 500


@status_bp.route('/<int:status_id>', methods=['GET'])
@jwt_required()
def view_status(status_id):
    """
    Decrypt a status's caption (and mark it viewed, unless you're the
    poster).
    ---
    tags:
      - Status
    parameters:
      - name: status_id
        in: path
        required: true
        type: integer
      - name: password
        in: query
        required: true
        type: string
    responses:
      200:
        description: Status decrypted
    """
    try:
        user_id = int(get_jwt_identity())
        password = request.args.get('password')
        if not password:
            return jsonify({'error': 'Password is required'}), 400

        result = StatusService.view_status(status_id, user_id, password)
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"View status error: {str(e)}")
        return jsonify({'error': 'Failed to view status'}), 500


def _stream_media(status_id):
    """Shared by the /media and legacy /image endpoints."""
    user_id = int(get_jwt_identity())
    # POST keeps the password out of the URL (and so out of browser history,
    # proxy logs and referrers); GET is kept for older clients.
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        password = body.get('password') or request.form.get('password')
    else:
        password = request.args.get('password')
    if not password:
        return jsonify({'error': 'Password is required'}), 400

    result = StatusService.get_status_media(status_id, user_id, password)
    if result.get('error'):
        return jsonify({'error': result['error']}), 400

    data = result['media_data']
    total = len(data)
    status_code = 200
    headers = {
        'Accept-Ranges': 'bytes',
        # Decrypted private content: never cache it, never let a browser
        # second-guess the type, and never let it run as a page.
        'Cache-Control': 'private, no-store',
        'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "default-src 'none'; sandbox",
        'X-Status-Media-Type': result['media_type'] or '',
    }

    # HTTP Range support, so a <video> pointed straight at this URL can seek.
    # (Werkzeug's send_file only does this for real files, not memory.)
    range_header = request.headers.get('Range')
    if range_header:
        m = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header.strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else total - 1
            else:                                   # "-N": the last N bytes
                start = max(0, total - int(m.group(2)))
                end = total - 1
            end = min(end, total - 1)
            if start >= total or start > end:
                return Response(status=416, headers={**headers, 'Content-Range': f'bytes */{total}'})
            data = data[start:end + 1]
            status_code = 206
            headers['Content-Range'] = f'bytes {start}-{end}/{total}'

    headers['Content-Length'] = str(len(data))
    return Response(data, status=status_code, mimetype=result['mime_type'], headers=headers)


@status_bp.route('/<int:status_id>/media', methods=['GET', 'POST'])
@jwt_required()
def get_status_media(status_id):
    """
    Stream a status's decrypted photo or video.
    ---
    tags:
      - Status
    parameters:
      - name: status_id
        in: path
        required: true
        type: integer
      - name: password
        in: body (POST, preferred) or query (GET)
        required: true
        type: string
    responses:
      200:
        description: Media streamed (supports HTTP Range requests)
    """
    try:
        return _stream_media(status_id)
    except Exception as e:
        logger.error(f"Get status media error: {str(e)}")
        return jsonify({'error': 'Failed to get status media'}), 500


@status_bp.route('/<int:status_id>/image', methods=['GET'])
@jwt_required()
def get_status_image(status_id):
    """
    Legacy alias of /media (kept for older clients).
    ---
    tags:
      - Status
    responses:
      200:
        description: Media streamed
    """
    try:
        return _stream_media(status_id)
    except Exception as e:
        logger.error(f"Get status image error: {str(e)}")
        return jsonify({'error': 'Failed to get status image'}), 500


@status_bp.route('/<int:status_id>/viewers', methods=['GET'])
@jwt_required()
def get_viewers(status_id):
    """
    Who has viewed one of your own statuses.
    ---
    tags:
      - Status
    parameters:
      - name: status_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Viewer list retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        result = StatusService.get_viewers(status_id, user_id)
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get status viewers error: {str(e)}")
        return jsonify({'error': 'Failed to get viewers'}), 500


@status_bp.route('/<int:status_id>', methods=['DELETE'])
@jwt_required()
def delete_status(status_id):
    """
    Delete your own status early.
    ---
    tags:
      - Status
    parameters:
      - name: status_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Status deleted
    """
    try:
        user_id = int(get_jwt_identity())
        result = StatusService.delete_status(status_id, user_id)
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Delete status error: {str(e)}")
        return jsonify({'error': 'Failed to delete status'}), 500