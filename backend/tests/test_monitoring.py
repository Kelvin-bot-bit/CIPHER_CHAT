# backend/tests/test_monitoring.py
"""
Tests for the monitoring / observability / audit work.

Run with:  pytest tests/test_monitoring.py -q
(Uses its own fixtures and an in-memory SQLite database.)
"""
import json
import os
import tempfile

import pytest

os.environ.setdefault('FLASK_ENV', 'development')


@pytest.fixture(scope='module')
def app():
    from app import create_app
    from config import TestingConfig
    from extensions import db

    class Cfg(TestingConfig):
        LOG_DIR = tempfile.mkdtemp(prefix='cipher-logs-')
        MAX_LOGIN_ATTEMPTS = 3
        LOCKOUT_TIME = 15
        SLOW_REQUEST_MS = 1000
        BCRYPT_LOG_ROUNDS = 4

    app = create_app(Cfg)

    @app.route('/api/_boom')
    def _boom():
        raise RuntimeError('kaboom secret-detail')

    @app.route('/api/_toobig')
    def _toobig():
        from werkzeug.exceptions import RequestEntityTooLarge
        raise RequestEntityTooLarge()

    with app.app_context():
        # The production schema reuses index names across tables (legal on
        # MySQL, rejected by SQLite), so make them unique for this test DB.
        for table in db.metadata.tables.values():
            for ix in table.indexes:
                if not ix.name.startswith(table.name):
                    ix.name = f'{table.name}__{ix.name}'
        db.create_all()
        yield app


@pytest.fixture(scope='module')
def users(app):
    from extensions import db
    from models import User
    from services.auth_service import AuthService

    def mk(username, is_admin=False):
        u = User(username=username, email=f'{username}@example.com',
                 password_hash=AuthService.bcrypt.generate_password_hash('Passw0rd!x').decode(),
                 full_name=username.title(), is_active=True, is_verified=True, is_admin=is_admin,
                 public_key='pk', encrypted_private_key='epk')
        db.session.add(u)
        db.session.commit()
        return u

    return {'admin': mk('boss', True), 'alice': mk('alice'), 'bob': mk('bob'),
            'carol': mk('carol'), 'dave': mk('dave'), 'erin': mk('erin')}


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


def login(client, ident, pw='Passw0rd!x', ip='10.0.0.1'):
    return client.post('/api/auth/login', json={'identifier': ident, 'password': pw},
                       environ_overrides={'REMOTE_ADDR': ip},
                       headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537.36'})


@pytest.fixture(scope='module')
def admin_headers(client, users):
    r = login(client, 'boss')
    assert r.status_code == 200, r.get_json()
    return {'Authorization': f"Bearer {r.get_json()['access_token']}"}


# ------------------------------------------------------------ failed logins
def test_failure_reasons_are_recorded(app, client, users):
    from models import LoginHistory
    assert login(client, 'nobody-here', ip='10.0.0.9').status_code == 401        # unknown user
    assert login(client, 'alice', pw='wrong', ip='10.0.0.9').status_code == 401  # wrong password

    rows = {r.failure_code: r for r in LoginHistory.query.filter_by(success=False).all()}
    assert rows['user_not_found'].user_id is None
    assert rows['user_not_found'].identifier == 'nobody-here'
    assert 'No account' in rows['user_not_found'].failure_reason
    assert rows['invalid_password'].user_id == users['alice'].id
    assert 'Incorrect password' in rows['invalid_password'].failure_reason


def test_response_does_not_reveal_which_part_was_wrong(client, users):
    a = login(client, 'ghost-account', ip='10.0.0.10').get_json()
    b = login(client, 'carol', pw='nope', ip='10.0.0.10').get_json()
    assert a['error'] == b['error'] == 'Invalid credentials'


def test_lockout_after_repeated_failures(client, users):
    for _ in range(3):
        assert login(client, 'bob', pw='bad', ip='10.0.0.20').status_code == 401
    r = login(client, 'bob', pw='bad', ip='10.0.0.20')
    assert r.status_code == 429
    # even the right password is refused while locked
    assert login(client, 'bob', ip='10.0.0.20').status_code == 429
    from models import LoginHistory
    assert LoginHistory.query.filter_by(failure_code='account_locked').count() >= 2


def test_account_state_only_revealed_with_correct_password(app, client, users):
    from extensions import db
    from models import LoginHistory
    users['dave'].is_suspended = True
    db.session.commit()
    assert login(client, 'dave', pw='wrong', ip='10.0.0.30').get_json()['error'] == 'Invalid credentials'
    assert login(client, 'dave', ip='10.0.0.30').get_json()['error'] == 'Account is suspended'
    assert LoginHistory.query.filter_by(failure_code='account_suspended').count() == 1
    users['dave'].is_suspended = False
    db.session.commit()


def test_successful_login_clears_failure_count(client, users):
    from models import LoginHistory
    login(client, 'erin', pw='bad', ip='10.0.0.40')
    login(client, 'erin', pw='bad', ip='10.0.0.40')
    assert LoginHistory.count_recent_failures(identifier='erin', user_id=users['erin'].id) == 2
    assert login(client, 'erin', ip='10.0.0.40').status_code == 200
    assert LoginHistory.count_recent_failures(identifier='erin', user_id=users['erin'].id) == 0


# --------------------------------------------------------------- audit logs
def test_audit_logs_show_real_user_details(client, users, admin_headers):
    r = client.get('/api/admin/audit-logs?per_page=200', headers=admin_headers)
    assert r.status_code == 200
    logs = r.get_json()['logs']
    login_ok = next(l for l in logs if l['action'] == 'login' and l['user']['username'] == 'alice' or
                    l['action'] == 'login' and l['user']['username'] == 'boss')
    u = login_ok['user']
    assert u['username'] and u['email'].endswith('@example.com') and u['full_name']
    assert u['deleted'] is False

    failed = [l for l in logs if l['action'] == 'login_failed']
    assert failed, 'failed logins must appear in the audit trail'
    assert all(isinstance(l['details'], dict) for l in failed), [l for l in failed if not l['details']][:2]
    reasons = {l['details']['reason'] for l in failed}
    assert any('Incorrect password' in x for x in reasons)
    assert any('No account' in x for x in reasons)
    unknown = next(l for l in failed if l['details']['identifier'] == 'nobody-here')
    assert unknown['details']['code'] == 'user_not_found'
    assert unknown['user']['username'] == 'nobody-here' and unknown['user']['unregistered'] is True
    assert isinstance(unknown['details'], dict)  # a real object, not a JSON string


def test_audit_details_are_not_double_encoded_and_secrets_are_redacted(app, users):
    from models import AuditLog
    row = AuditLog.log_action(users['alice'].id, 'test_action',
                              details={'password': 'hunter2', 'note': 'x', 'nested': {'token': 'abc'}})
    d = row.to_dict()['details']
    assert d == {'password': '[REDACTED]', 'note': 'x', 'nested': {'token': '[REDACTED]'}}
    # legacy rows (stored as a JSON string) are still readable
    from utils.redact import parse_json_details
    assert parse_json_details(json.dumps(json.dumps({'a': 1}))) == {'a': 1}


def test_deleted_users_keep_their_name_in_the_trail(app, client, users, admin_headers):
    from extensions import db
    from models import User, AuditLog
    from services.auth_service import AuthService
    tmp = User(username='temp_user', email='temp@example.com', full_name='Temp User',
               password_hash=AuthService.bcrypt.generate_password_hash('x').decode(), is_active=True, is_verified=True,
               public_key='pk', encrypted_private_key='epk')
    db.session.add(tmp)
    db.session.commit()
    tid = tmp.id
    AuditLog.log_action(tid, 'something_by_temp')
    r = client.delete(f'/api/admin/users/{tid}', headers=admin_headers)
    assert r.status_code == 200
    logs = client.get('/api/admin/audit-logs?q=temp_user&per_page=50', headers=admin_headers).get_json()['logs']
    by_temp = next(l for l in logs if l['action'] == 'something_by_temp')
    assert by_temp['user']['username'] == 'temp_user' and by_temp['user']['deleted'] is True
    deletion = next(l for l in logs if l['action'] == 'admin_delete_user')
    assert deletion['details']['target']['email'] == 'temp@example.com'
    assert deletion['user']['username'] == 'boss'


def test_audit_filters_and_export(client, admin_headers):
    r = client.get('/api/admin/audit-logs?status=failure&per_page=100', headers=admin_headers).get_json()
    assert r['total'] > 0 and all(l['status'] == 'failure' for l in r['logs'])
    r = client.get('/api/admin/audit-logs?q=alice', headers=admin_headers).get_json()
    assert r['total'] > 0
    csv_resp = client.get('/api/admin/audit-logs/export?action=login_failed', headers=admin_headers)
    assert csv_resp.status_code == 200 and 'Incorrect password' in csv_resp.get_data(as_text=True)
    acts = client.get('/api/admin/audit-logs/actions', headers=admin_headers).get_json()['actions']
    assert any(a['action'] == 'login_failed' for a in acts)


def test_login_attempts_endpoints(client, admin_headers):
    r = client.get('/api/admin/login-attempts?outcome=failed', headers=admin_headers).get_json()
    assert r['total'] > 0
    assert all(a['success'] is False and a['failure_reason'] for a in r['attempts'])
    unknown = next(a for a in r['attempts'] if a['identifier'] == 'nobody-here')
    assert unknown['failure_code'] == 'user_not_found' and unknown['user'] is None
    s = client.get('/api/admin/login-attempts/summary', headers=admin_headers).get_json()
    codes = {x['code'] for x in s['by_reason']}
    assert {'user_not_found', 'invalid_password', 'account_locked'} <= codes
    assert any(l['identifier'] == 'bob' for l in s['locked_accounts'])
    assert s['top_ips'] and s['trend']


def test_statistics_unique_users_is_a_real_distinct_count(client, admin_headers):
    r = client.get('/api/admin/statistics', headers=admin_headers).get_json()
    logins = next(v for v in r.values() if isinstance(v, dict) and 'unique_users' in v)
    assert 0 < logins['unique_users'] <= 6          # 6 seeded accounts - not "one per login row"
    assert logins['failed_24h'] > 0


# -------------------------------------------------------------- observability
def test_request_ids_and_timing_headers(client):
    r = client.get('/health')
    assert r.headers['X-Request-ID'] and r.headers['X-Response-Time'].endswith('ms')
    r = client.get('/health', headers={'X-Request-ID': 'trace-abc-12345'})
    assert r.headers['X-Request-ID'] == 'trace-abc-12345'
    r = client.get('/health', headers={'X-Request-ID': 'bad id with spaces!'})
    assert r.headers['X-Request-ID'] != 'bad id with spaces!'


def test_monitoring_requires_admin(app, users):
    anon = app.test_client()                      # separate cookie jar
    assert anon.get('/api/admin/monitoring/overview').status_code == 401
    tok = login(anon, 'alice').get_json()['access_token']
    r = anon.get('/api/admin/monitoring/overview', headers={'Authorization': f'Bearer {tok}'})
    assert r.status_code == 403
    r = anon.get('/api/admin/users', headers={'Authorization': f'Bearer {tok}'})
    assert r.status_code == 403
    # the refused attempts are themselves recorded as security events
    from models import SystemEvent
    assert SystemEvent.query.filter_by(event='admin_access_denied').count() >= 1


def test_overview_metrics_logs_and_requests(client, admin_headers):
    for _ in range(5):
        client.get('/health')
    client.get('/api/does-not-exist')
    o = client.get('/api/admin/monitoring/overview', headers=admin_headers).get_json()
    assert o['status'] in ('ok', 'degraded')
    assert o['live']['requests'] > 0 and o['live']['p95_ms'] is not None
    assert o['database']['latency_ms'] is not None
    assert o['security']['failed_logins_24h'] > 0

    reqs = client.get('/api/admin/monitoring/requests?limit=50', headers=admin_headers).get_json()['requests']
    assert any(r['route'] == '/health' and r['status'] == 200 for r in reqs)
    assert all('/monitoring' not in r['path'] for r in reqs)        # dashboard polling is excluded
    assert any(r['status'] == 404 for r in client.get(
        '/api/admin/monitoring/requests?status=4xx', headers=admin_headers).get_json()['requests'])

    logs = client.get('/api/admin/monitoring/logs?level=WARNING', headers=admin_headers).get_json()['logs']
    assert any('Failed login' in l['message'] for l in logs)

    ts = client.get('/api/admin/monitoring/timeseries?minutes=30', headers=admin_headers).get_json()['points']
    assert len(ts) == 30 and sum(p['requests'] for p in ts) > 0
    ep = client.get('/api/admin/monitoring/endpoints', headers=admin_headers).get_json()['endpoints']
    assert any(e['route'] == '/health' for e in ep)


def test_health_checks_cover_every_subsystem(client, admin_headers):
    h = client.get('/api/admin/monitoring/health?refresh=1', headers=admin_headers).get_json()
    assert set(h['checks']) == {'database', 'storage', 'encryption', 'scheduler', 'realtime', 'process',
                                'configuration'}
    assert h['checks']['database']['status'] == 'ok'
    assert h['checks']['database']['details']['tables']['users'] >= 4
    assert h['checks']['encryption']['status'] == 'ok'
    assert client.get('/health/ready').status_code == 200


def test_unhandled_exception_is_logged_alerted_and_response_is_safe(app, client, admin_headers):
    r = client.get('/api/_boom')
    assert r.status_code == 500
    assert 'kaboom' not in r.get_data(as_text=True)          # internals are not leaked to the caller

    alerts = client.get('/api/admin/monitoring/alerts', headers=admin_headers).get_json()['alerts']
    a = next(a for a in alerts if a['rule'] == 'unhandled_exception')
    assert a['severity'] == 'critical' and 'RuntimeError' in a['title']
    assert 'Traceback' in a['details']['traceback']

    events = client.get('/api/admin/monitoring/events?level=ERROR', headers=admin_headers).get_json()['events']
    assert any(e['event'] == 'unhandled_exception' for e in events)
    assert any(e['event'] == 'server_error' and e['status_code'] == 500 for e in events)

    logs = client.get('/api/admin/monitoring/logs?level=ERROR', headers=admin_headers).get_json()['logs']
    assert any(l['exception'] and 'RuntimeError' in l['exception'] for l in logs)


def test_http_errors_are_not_reported_as_crashes(app, client):
    assert client.get('/api/_toobig').status_code == 413


def test_alert_lifecycle(app, client, admin_headers):
    from services import alert_service
    alert_service.raise_alert('error_rate', 'warning', 'Elevated server error rate', 'x', fingerprint='t:fp')
    _, is_new = alert_service.raise_alert('error_rate', 'critical', 'Very high error rate', 'y', fingerprint='t:fp')
    assert is_new is False                                    # deduplicated into the same alert
    alerts = client.get('/api/admin/monitoring/alerts', headers=admin_headers).get_json()['alerts']
    a = next(a for a in alerts if a['fingerprint'] == 't:fp')
    assert a['occurrences'] == 2 and a['severity'] == 'critical'    # escalated

    r = client.post(f"/api/admin/monitoring/alerts/{a['id']}/acknowledge", headers=admin_headers)
    assert r.get_json()['alert']['status'] == 'acknowledged'
    assert r.get_json()['alert']['acknowledged_by'] == 'boss'
    r = client.post(f"/api/admin/monitoring/alerts/{a['id']}/resolve", headers=admin_headers)
    assert r.get_json()['alert']['status'] == 'resolved'
    active = client.get('/api/admin/monitoring/alerts', headers=admin_headers).get_json()['alerts']
    assert all(x['fingerprint'] != 't:fp' for x in active)
    rules = client.get('/api/admin/monitoring/alerts/rules', headers=admin_headers).get_json()
    assert len(rules['rules']) >= 10 and rules['channels']['dashboard'] is True
    assert client.post('/api/admin/monitoring/alerts/test', headers=admin_headers).status_code == 200


def test_alert_rules_detect_brute_force_and_stuffing(app):
    from services import monitoring_service
    for i in range(9):
        with app.test_request_context(environ_base={'REMOTE_ADDR': '203.0.113.7'}):
            from services.auth_service import AuthService
            AuthService.login_user(f'victim{i % 6}', 'guess', ip_address='203.0.113.7', user_agent='curl/8')
    firing = {f['fingerprint']: f for f in monitoring_service.evaluate_rules()}
    assert 'auth:brute_force:203.0.113.7' in firing and firing['auth:brute_force:203.0.113.7']['severity'] == 'critical'
    assert 'auth:stuffing:203.0.113.7' in firing


def test_auto_audit_of_writes_and_admin_change_alert(client, users, admin_headers):
    r = client.put(f"/api/admin/users/{users['alice'].id}", json={'is_admin': True, 'full_name': 'Alice A'},
                   headers=admin_headers)
    assert r.status_code == 200
    log = next(l for l in client.get('/api/admin/audit-logs?action=admin_update_user',
                                     headers=admin_headers).get_json()['logs'])
    ch = log['details']['changes']
    assert ch['is_admin'] == {'from': False, 'to': True} and ch['full_name']['to'] == 'Alice A'
    assert log['target']['username'] == 'alice' and log['user']['username'] == 'boss'
    alerts = client.get('/api/admin/monitoring/alerts', headers=admin_headers).get_json()['alerts']
    assert any(a['rule'] == 'admin_change' and 'granted' in a['title'] for a in alerts)
    client.put(f"/api/admin/users/{users['alice'].id}", json={'is_admin': False}, headers=admin_headers)


def test_structured_json_log_files_and_redaction(app):
    import logging
    from utils.logger import log_error
    logging.getLogger('t').error('hello', extra={'fields': {'password': 'hunter2-value', 'ok': 1}})
    for h in logging.getLogger().handlers:
        h.flush()
    # Logging is configured once per process, so ask the handlers where the files really are
    # (they are not in this suite's own LOG_DIR if another test module created the app first).
    paths = {os.path.basename(h.baseFilename): h.baseFilename for h in logging.getLogger().handlers
             if hasattr(h, 'baseFilename')}
    paths['access.log'] = next(h.baseFilename for h in logging.getLogger('access').handlers)
    app_log = open(paths['app.log'], encoding='utf-8').read()
    assert '"password": "[REDACTED]"' in app_log and 'hunter2-value' not in app_log
    line = json.loads(app_log.strip().splitlines()[-1])
    assert {'timestamp', 'level', 'logger', 'message'} <= set(line)
    access = open(paths['access.log'], encoding='utf-8').read().strip().splitlines()
    rec = json.loads(access[-1])
    assert rec['method'] and 'duration_ms' in rec and 'request_id' in rec


def test_client_ip_ignores_spoofed_forwarded_for_unless_trusted(app, client, users):
    from models import LoginHistory
    h = {'X-Forwarded-For': '8.8.8.8', 'User-Agent': 'x'}
    client.post('/api/auth/login', json={'identifier': 'spoof-1', 'password': 'x'}, headers=h,
                environ_overrides={'REMOTE_ADDR': '10.9.9.9'})
    row = LoginHistory.query.filter_by(identifier='spoof-1').one()
    assert row.ip_address == '10.9.9.9'                      # header ignored by default

    app.config['TRUST_PROXY_HEADERS'] = True
    try:
        client.post('/api/auth/login', json={'identifier': 'spoof-2', 'password': 'x'}, headers=h,
                    environ_overrides={'REMOTE_ADDR': '10.9.9.9'})
        assert LoginHistory.query.filter_by(identifier='spoof-2').one().ip_address == '8.8.8.8'
    finally:
        app.config['TRUST_PROXY_HEADERS'] = False


def test_library_chatter_stays_out_of_the_dashboard_but_warnings_get_through(app):
    import logging
    from services.telemetry import telemetry
    logging.getLogger('engineio.server').info('Sending packet MESSAGE data 0')
    logging.getLogger('sqlalchemy.engine.Engine').info('SELECT * FROM users WHERE email = ?')
    logging.getLogger('engineio.server').warning('bad handshake')
    msgs = [l['message'] for l in telemetry.get_logs(limit=200)]
    assert not any('Sending packet' in m or 'SELECT * FROM users' in m for m in msgs)
    assert 'bad handshake' in msgs


def test_successful_login_request_is_attributed_to_the_user(client, users):
    from services.telemetry import telemetry
    login(client, 'erin', ip='10.0.0.77')
    rec = next(r for r in telemetry.get_requests(limit=50, q='auth/login') if r['status'] == 200)
    assert rec['username'] == 'erin'
