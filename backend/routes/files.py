# backend/routes/files.py
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.file_service import FileService
from services.message_service import MessageService
from models import File, Message
from extensions import db
import logging
import io

files_bp = Blueprint('files', __name__)
logger = logging.getLogger(__name__)

@files_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_file():
    """
    Upload a file
    ---
    tags:
      - Files
    parameters:
      - name: file
        in: formData
        required: true
        type: file
      - name: message_id
        in: formData
        type: integer
      - name: password
        in: formData
        required: true
        type: string
    responses:
      200:
        description: File uploaded successfully
    """
    try:
        user_id = int(get_jwt_identity())
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        message_id = request.form.get('message_id', type=int)
        password = request.form.get('password')
        
        if not password:
            return jsonify({'error': 'Password required for encryption'}), 400
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Read file data
        file_data = file.read()
        
        # Upload file
        result = FileService.upload_file(
            file_data=file_data,
            filename=file.filename,
            uploader_id=user_id,
            message_id=message_id,
            mime_type=file.content_type,
            uploader_password=password
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'message': 'File uploaded successfully',
            'file': result['file']
        }), 200
        
    except Exception as e:
        logger.error(f"Upload file error: {str(e)}")
        return jsonify({'error': 'Failed to upload file'}), 500

@files_bp.route('/download/<int:file_id>', methods=['GET'])
@jwt_required()
def download_file(file_id):
    """
    Download a file
    ---
    tags:
      - Files
    parameters:
      - name: file_id
        in: path
        required: true
        type: integer
      - name: password
        in: query
        required: true
        type: string
    responses:
      200:
        description: File downloaded successfully
    """
    try:
        user_id = int(get_jwt_identity())
        password = request.args.get('password')
        
        if not password:
            return jsonify({'error': 'Password required for decryption'}), 400
        
        result = FileService.download_file(file_id, user_id, password)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        # Send file
        return send_file(
            io.BytesIO(result['file_data']),
            as_attachment=True,
            download_name=result['file_name'],
            mimetype=result['mime_type']
        )
        
    except Exception as e:
        logger.error(f"Download file error: {str(e)}")
        return jsonify({'error': 'Failed to download file'}), 500

@files_bp.route('/<int:file_id>', methods=['DELETE'])
@jwt_required()
def delete_file(file_id):
    """
    Delete a file
    ---
    tags:
      - Files
    parameters:
      - name: file_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: File deleted successfully
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FileService.delete_file(file_id, user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'message': 'File deleted successfully'}), 200
        
    except Exception as e:
        logger.error(f"Delete file error: {str(e)}")
        return jsonify({'error': 'Failed to delete file'}), 500

@files_bp.route('/my-files', methods=['GET'])
@jwt_required()
def get_my_files():
    """
    Get user's files
    ---
    tags:
      - Files
    responses:
      200:
        description: User's files retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FileService.get_user_files(user_id)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get user files error: {str(e)}")
        return jsonify({'error': 'Failed to get user files'}), 500

@files_bp.route('/message/<int:message_id>', methods=['GET'])
@jwt_required()
def get_message_files(message_id):
    """
    Get files attached to a message
    ---
    tags:
      - Files
    parameters:
      - name: message_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Message files retrieved
    """
    try:
        user_id = int(get_jwt_identity())
        
        result = FileService.get_message_files(message_id, user_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get message files error: {str(e)}")
        return jsonify({'error': 'Failed to get message files'}), 500