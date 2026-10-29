# backend/routes/voice.py
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.voice_service import VoiceService
import io
import logging

voice_bp = Blueprint('voice', __name__)
logger = logging.getLogger(__name__)


@voice_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_voice():
    """
    Upload a voice recording, attached to an existing message
    ---
    tags:
      - Voice
    parameters:
      - name: audio
        in: formData
        required: true
        type: file
      - name: message_id
        in: formData
        required: true
        type: integer
      - name: duration
        in: formData
        required: true
        type: integer
      - name: password
        in: formData
        type: string
        description: Required only when the message is in a group chat (needed to unwrap the group key)
    responses:
      200:
        description: Voice note uploaded successfully
    """
    try:
        user_id = int(get_jwt_identity())

        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        audio = request.files['audio']
        message_id = request.form.get('message_id', type=int)
        duration = request.form.get('duration', type=int)
        password = request.form.get('password')

        if not message_id:
            return jsonify({'error': 'message_id is required'}), 400
        if duration is None or duration <= 0:
            return jsonify({'error': 'A valid duration (in seconds) is required'}), 400
        if audio.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400

        audio_data = audio.read()

        result = VoiceService.upload_voice_note(
            file_data=audio_data,
            filename=audio.filename,
            message_id=message_id,
            duration=duration,
            uploader_id=user_id,
            uploader_password=password
        )

        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        return jsonify({
            'message': 'Voice note uploaded successfully',
            'voice_note': result['voice_note']
        }), 200

    except Exception as e:
        logger.error(f"Upload voice note error: {str(e)}")
        return jsonify({'error': 'Failed to upload voice note'}), 500


@voice_bp.route('/download/<int:voice_note_id>', methods=['GET'])
@jwt_required()
def download_voice(voice_note_id):
    """
    Download and decrypt a voice note's audio
    ---
    tags:
      - Voice
    parameters:
      - name: voice_note_id
        in: path
        required: true
        type: integer
      - name: password
        in: query
        required: true
        type: string
    responses:
      200:
        description: Voice note audio streamed
    """
    try:
        user_id = int(get_jwt_identity())
        password = request.args.get('password')

        result = VoiceService.download_voice_note(voice_note_id, user_id, password)

        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        # Recordings are always captured as audio/webm;codecs=opus by the
        # frontend (Chrome/Firefox/Edge) — see VoiceRecorderModal.jsx. This
        # is a known limitation, not something this endpoint can detect: the
        # VoiceNote model has no mime_type column, so the original format
        # isn't tracked per-recording. Safari's MediaRecorder support for
        # audio/webm is inconsistent, so voice notes recorded there may not
        # play back correctly for a recipient — flagged in the frontend too.
        return send_file(
            io.BytesIO(result['audio_data']),
            mimetype='audio/webm',
            as_attachment=False,
            download_name=f'voice-note-{voice_note_id}.webm'
        )

    except Exception as e:
        logger.error(f"Download voice note error: {str(e)}")
        return jsonify({'error': 'Failed to download voice note'}), 500


@voice_bp.route('/message/<int:message_id>', methods=['GET'])
@jwt_required()
def get_voice_for_message(message_id):
    """
    Get the voice note attached to a message, if any
    ---
    tags:
      - Voice
    parameters:
      - name: message_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Voice note retrieved
    """
    try:
        user_id = int(get_jwt_identity())

        result = VoiceService.get_voice_note_for_message(message_id, user_id)

        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Get voice note error: {str(e)}")
        return jsonify({'error': 'Failed to get voice note'}), 500