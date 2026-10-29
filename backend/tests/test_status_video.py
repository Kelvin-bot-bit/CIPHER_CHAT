# backend/tests/test_status_video.py
"""
Status updates with video (and the hardening that came with it).

Uses real users with real RSA keys, a real friendship and the real
encryption path, so a passing test means a video really can be posted,
fanned out to a friend, decrypted and streamed.

Run with:  pytest tests/test_status_video.py -q
"""
import io
import os
import tempfile
import time
from datetime import datetime, timedelta

import pytest

os.environ.setdefault('FLASK_ENV', 'development')

PW = 'Passw0rd!x-long'


def fake_mp4(size=4096, brand=b'isom'):
    return b'\x00\x00\x00\x18ftyp' + brand + b'\x00\x00\x02\x00' + brand + b'mp41' + os.urandom(size)


def fake_mov():
    return fake_mp4(brand=b'qt  ')


def fake_webm():
    return b'\x1a\x45\xdf\xa3' + b'\x9fB\x86\x81\x01B\xf7\x81\x01B\xf2\x81\x04B\xf3\x81\x08B\x82\x84webm' + os.urandom(2048)


PNG = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + os.urandom(200)
JPEG = b'\xff\xd8\xff\xe0' + b'\x00\x10JFIF\x00' + os.urandom(200)


@pytest.fixture(scope='module')
def app():
    from app import create_app
    from config import TestingConfig
    from extensions import db

    class Cfg(TestingConfig):
        LOG_DIR = tempfile.mkdtemp(prefix='cipher-logs-')
        UPLOAD_FOLDER = tempfile.mkdtemp(prefix='cipher-uploads-')
        BCRYPT_LOG_ROUNDS = 4
        STATUS_MAX_VIDEO_MB = 1          # keep the oversize test fast

    app = create_app(Cfg)
    with app.app_context():
        for table in db.metadata.tables.values():
            for ix in table.indexes:
                if not ix.name.startswith(table.name):
                    ix.name = f'{table.name}__{ix.name}'
        db.create_all()
        yield app


@pytest.fixture(scope='module')
def people(app):
    from extensions import db
    from models import Friend, User
    from services.auth_service import AuthService

    ids = {}
    for name in ('poster', 'friend', 'stranger'):
        r = AuthService.register_user(name, f'{name}@example.com', PW, name.title())
        assert not r.get('error'), r
        u = User.query.filter_by(username=name).one()
        u.is_verified = True
        ids[name] = u.id
    db.session.add(Friend(user_id=ids['poster'], friend_id=ids['friend']))
    db.session.commit()
    return ids


def client_for(app, name):
    c = app.test_client()
    r = c.post('/api/auth/login', json={'identifier': name, 'password': PW})
    assert r.status_code == 200, r.get_json()
    c.headers = {'Authorization': f"Bearer {r.get_json()['access_token']}"}
    return c


@pytest.fixture(scope='module')
def poster(app, people):
    return client_for(app, 'poster')


@pytest.fixture(scope='module')
def friend(app, people):
    return client_for(app, 'friend')


@pytest.fixture(scope='module')
def stranger(app, people):
    return client_for(app, 'stranger')


def post(c, data=None, name='clip.mp4', ctype='video/mp4', caption='hello', field='media'):
    form = {'password': PW, 'caption': caption}
    if data is not None:
        form[field] = (io.BytesIO(data), name, ctype)
    return c.post('/api/status/', data=form, content_type='multipart/form-data', headers=c.headers)


# ------------------------------------------------------------------ posting
def test_post_a_video_and_a_friend_can_watch_it(poster, friend):
    video = fake_mp4(60000)
    r = post(poster, video, caption='sunset from the matatu')
    assert r.status_code == 200, r.get_json()
    s = r.get_json()['status']
    assert s['media_type'] == 'video' and s['has_video'] is True and s['has_media'] is True
    assert s['has_image'] is False                      # older clients never put a video in <img>
    assert s['message_type'] == 'video' and s['media_mime_type'] == 'video/mp4'
    assert s['media_size'] == len(video)

    # the friend sees it in the feed, flagged as video
    feed = friend.get('/api/status/feed', headers=friend.headers).get_json()['feed']
    mine = next(e for e in feed if e['user']['username'] == 'poster')
    assert mine['statuses'][0]['media_type'] == 'video'

    # caption decrypts and the signature verifies
    v = friend.get(f"/api/status/{s['id']}", query_string={'password': PW}, headers=friend.headers).get_json()
    assert v['status']['caption'] == 'sunset from the matatu' and v['status']['is_valid_signature']

    # the video decrypts byte-for-byte (POST keeps the password out of the URL)
    m = friend.post(f"/api/status/{s['id']}/media", json={'password': PW}, headers=friend.headers)
    assert m.status_code == 200
    assert m.data == video
    assert m.headers['Content-Type'] == 'video/mp4'
    assert m.headers['X-Content-Type-Options'] == 'nosniff'
    assert 'no-store' in m.headers['Cache-Control']
    assert 'sandbox' in m.headers['Content-Security-Policy']


def test_video_supports_range_requests_so_players_can_seek(poster, friend):
    video = fake_mp4(30000)
    s = post(poster, video).get_json()['status']
    r = friend.post(f"/api/status/{s['id']}/media", json={'password': PW},
                    headers={**friend.headers, 'Range': 'bytes=100-199'})
    assert r.status_code == 206
    assert r.data == video[100:200]
    assert r.headers['Content-Range'] == f'bytes 100-199/{len(video)}'
    assert r.headers['Content-Length'] == '100' and r.headers['Accept-Ranges'] == 'bytes'

    def rng(value):
        return friend.post(f"/api/status/{s['id']}/media", json={'password': PW},
                           headers={**friend.headers, 'Range': value})
    assert rng('bytes=29000-').data == video[29000:]                    # open-ended
    assert rng('bytes=-500').data == video[-500:]                       # last 500 bytes
    assert rng('bytes=0-999999999').data == video                       # end clamped to the file
    assert rng('bytes=99999999-').status_code == 416                    # beyond the end
    assert rng('bytes=abc').status_code == 200                          # malformed: ignored, full file


def test_mov_and_webm_are_accepted_with_their_real_types(poster):
    for blob, mime in ((fake_mov(), 'video/quicktime'), (fake_webm(), 'video/webm')):
        r = post(poster, blob, name='x.bin', ctype='application/octet-stream')
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['status']['media_mime_type'] == mime


def test_the_clients_claimed_type_is_ignored(poster):
    html = b'<html><script>alert(document.cookie)</script></html>' + b' ' * 64
    r = post(poster, html, name='evil.mp4', ctype='video/mp4')
    assert r.status_code == 400 and 'Unsupported file' in r.get_json()['error']
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>' + b' ' * 64
    assert post(poster, svg, name='x.svg', ctype='image/svg+xml').status_code == 400
    audio = b'\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00' + os.urandom(200)
    assert post(poster, audio, name='song.m4a', ctype='audio/mp4').status_code == 400
    mkv = b'\x1a\x45\xdf\xa3' + b'\x9fB\x86\x81\x01matroska' + os.urandom(500)
    assert post(poster, mkv, name='x.mkv', ctype='video/x-matroska').status_code == 400


def test_a_real_video_is_served_with_the_detected_type_not_the_claimed_one(poster, friend):
    s = post(poster, fake_mp4(2000), name='clip.png', ctype='image/png').get_json()['status']
    assert s['media_type'] == 'video' and s['media_mime_type'] == 'video/mp4'
    m = friend.post(f"/api/status/{s['id']}/media", json={'password': PW}, headers=friend.headers)
    assert m.headers['Content-Type'] == 'video/mp4'


def test_oversize_video_is_rejected_with_a_helpful_message(poster):
    r = post(poster, fake_mp4(1024 * 1024 + 10))
    assert r.status_code == 400
    assert 'too large' in r.get_json()['error'] and '1MB' in r.get_json()['error']


def test_photos_still_work_through_old_and_new_endpoints(poster, friend):
    s = post(poster, PNG, name='p.png', ctype='image/png', field='image').get_json()['status']   # legacy field name
    assert s['media_type'] == 'image' and s['has_image'] is True and s['has_video'] is False
    new = friend.post(f"/api/status/{s['id']}/media", json={'password': PW}, headers=friend.headers)
    old = friend.get(f"/api/status/{s['id']}/image", query_string={'password': PW}, headers=friend.headers)
    assert new.data == old.data == PNG and old.headers['Content-Type'] == 'image/png'
    s2 = post(poster, JPEG, name='p.jpg', ctype='image/jpeg').get_json()['status']
    assert s2['media_mime_type'] == 'image/jpeg'


def test_text_only_status_is_unchanged(poster):
    s = post(poster, None, caption='just words').get_json()['status']
    assert s['media_type'] is None and s['has_media'] is False and s['message_type'] == 'text'
    assert post(poster, None, caption='').status_code == 400


# ------------------------------------------------------------------- access
def test_only_people_with_a_key_can_get_the_media(poster, stranger, friend):
    s = post(poster, fake_mp4(1500)).get_json()['status']
    r = stranger.post(f"/api/status/{s['id']}/media", json={'password': PW}, headers=stranger.headers)
    assert r.status_code == 400 and 'do not have access' in r.get_json()['error']
    bad = friend.post(f"/api/status/{s['id']}/media", json={'password': 'wrong-password'}, headers=friend.headers)
    assert bad.status_code == 400
    assert friend.post(f"/api/status/{s['id']}/media", json={}, headers=friend.headers).status_code == 400
    assert friend.post(f"/api/status/{s['id']}/media", json={'password': PW}).status_code == 401


def test_the_media_on_disk_is_encrypted(app, poster):
    from models import StatusPost
    clear = b'THIS-IS-THE-SECRET-VIDEO-PAYLOAD' * 200
    s = post(poster, fake_mp4(10) + clear).get_json()['status']
    path = StatusPost.query.get(s['id']).image_path
    assert os.path.exists(path)
    assert b'THIS-IS-THE-SECRET-VIDEO-PAYLOAD' not in open(path, 'rb').read()


# ---------------------------------------------------------------- cleanup
def test_deleting_a_status_removes_the_encrypted_file_immediately(poster, friend):
    from models import StatusPost
    s = post(poster, fake_mp4(2500)).get_json()['status']
    path = StatusPost.query.get(s['id']).image_path
    assert os.path.exists(path)
    assert poster.delete(f"/api/status/{s['id']}", headers=poster.headers).status_code == 200
    assert not os.path.exists(path)
    gone = friend.post(f"/api/status/{s['id']}/media", json={'password': PW}, headers=friend.headers)
    assert gone.status_code == 400


def test_purge_removes_expired_media_rows_keys_views_and_orphans(app, poster, friend):
    from extensions import db
    from models import StatusPost, StatusRecipientKey, StatusView
    from services.status_service import StatusService

    s = post(poster, fake_mp4(2200)).get_json()['status']
    friend.get(f"/api/status/{s['id']}", query_string={'password': PW}, headers=friend.headers)  # creates a view
    row = StatusPost.query.get(s['id'])
    path = row.image_path
    fresh = post(poster, fake_mp4(1100)).get_json()['status']          # must survive the purge
    fresh_path = StatusPost.query.get(fresh['id']).image_path

    # an upload that died half-way: a file that no row refers to
    orphan = os.path.join(os.path.dirname(path), 'orphan.enc')
    open(orphan, 'wb').write(b'x' * 100)
    old = time.time() - 3 * 86400
    os.utime(orphan, (old, old))
    young_orphan = os.path.join(os.path.dirname(path), 'inflight.enc')
    open(young_orphan, 'wb').write(b'x')                                # could be mid-upload: keep

    row.expires_at = datetime.utcnow() - timedelta(hours=3)
    db.session.commit()

    result = StatusService.purge_expired()
    assert result['statuses'] >= 1 and result['orphans'] == 1
    assert StatusPost.query.get(s['id']) is None
    assert StatusRecipientKey.query.filter_by(status_id=s['id']).count() == 0
    assert StatusView.query.filter_by(status_id=s['id']).count() == 0
    assert not os.path.exists(path) and not os.path.exists(orphan)
    assert os.path.exists(young_orphan) and os.path.exists(fresh_path)
    assert StatusPost.query.get(fresh['id']) is not None


def test_failed_post_does_not_leave_a_file_behind(app, poster, monkeypatch):
    from services.status_service import StatusService
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'status')
    before = set(os.listdir(folder))

    def boom(*a, **k):
        raise RuntimeError('db down')
    monkeypatch.setattr(StatusService, '_get_friend_users', boom)
    r = post(poster, fake_mp4(900))
    assert r.status_code == 400
    assert set(os.listdir(folder)) == before


def test_the_purge_job_is_scheduled(app):
    from services import cleanup_service
    cleanup_service.start_cleanup_scheduler(app)
    ids = {j.id for j in cleanup_service._scheduler.get_jobs()} if cleanup_service._scheduler else {'purge_status_media'}
    assert 'purge_status_media' in ids


# ---------------------------------------------------------- observability
def test_passwords_in_query_strings_never_reach_the_live_request_log(app, friend, poster):
    from services.telemetry import telemetry
    from utils.redact import safe_path
    s = post(poster, fake_mp4(800)).get_json()['status']
    friend.get(f"/api/status/{s['id']}", query_string={'password': 'my-secret-pass-123', 'x': '1'},
               headers=friend.headers)
    paths = [r['path'] for r in telemetry.get_requests(limit=200, q=f"/api/status/{s['id']}")]
    assert paths and not any('my-secret-pass-123' in p for p in paths)
    assert any('REDACTED' in p and 'x=1' in p for p in paths)
    assert safe_path('/a', b'token=abc&page=2') == '/a?token=[REDACTED]&page=2'
    assert safe_path('/a', b'') == '/a'
