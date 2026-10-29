# backend/services/monitoring_service.py
"""
Health checks, alert rules and the background evaluator.

``run_health_checks`` probes every moving part (database, storage, crypto,
scheduler, realtime, process, configuration). ``evaluate_rules`` turns those
probes plus live request telemetry and recent login failures into alerts.
The evaluator runs every MONITOR_INTERVAL_SECONDS in the background.
"""
import logging
import os
import platform
import shutil
import sys
import threading
import time
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import text

from extensions import db
from services import alert_service
from services.event_service import (independent_session, purge_old_records, record_event,
                                    suppress_telemetry)
from services.telemetry import telemetry, iso

logger = logging.getLogger(__name__)

_cache = {'t': 0, 'data': None}
_cache_lock = threading.Lock()
_last_status = {}
_table_counts = {'t': 0, 'data': None}
_dir_size = {'t': 0, 'data': None}
_ok_streak = {}
_scheduler = None


def _ms(t0):
    return round((time.perf_counter() - t0) * 1000, 2)


# ===================================================================== checks
def check_database():
    cfg = current_app.config
    res = {'status': 'ok', 'latency_ms': None, 'details': {}}
    dialect = db.engine.dialect.name
    res['details']['engine'] = dialect
    try:
        with suppress_telemetry():
            lat = []
            with db.engine.connect() as conn:
                for _ in range(3):
                    t0 = time.perf_counter()
                    conn.execute(text('SELECT 1'))
                    lat.append(_ms(t0))
                res['latency_ms'] = round(sum(lat) / len(lat), 2)
                res['details']['latency_samples_ms'] = lat

                if dialect == 'mysql':
                    try:
                        row = conn.execute(text('SELECT VERSION(), @@max_connections, @@read_only')).one()
                        res['details']['version'] = row[0]
                        res['details']['max_connections'] = int(row[1])
                        if int(row[2]) == 1:
                            res['status'] = 'fail'
                            res['details']['read_only'] = True
                            res['message'] = 'Database is in read-only mode; writes will fail.'
                        st = dict(conn.execute(text(
                            "SHOW GLOBAL STATUS WHERE Variable_name IN ('Threads_connected','Threads_running',"
                            "'Uptime','Slow_queries','Aborted_connects','Max_used_connections')")).all())
                        st = {k: int(v) for k, v in st.items()}
                        res['details']['server'] = st
                        if st.get('Threads_connected') is not None:
                            res['details']['connection_usage_pct'] = round(
                                100.0 * st['Threads_connected'] / max(1, res['details']['max_connections']), 1)
                        size = conn.execute(text(
                            'SELECT COALESCE(SUM(data_length + index_length), 0) FROM information_schema.tables '
                            'WHERE table_schema = DATABASE()')).scalar()
                        res['details']['size_mb'] = round(float(size) / 1024 / 1024, 2)
                    except Exception as exc:
                        res['details']['server_stats_error'] = str(exc)[:150]
                elif dialect == 'sqlite':
                    res['details']['version'] = conn.execute(text('select sqlite_version()')).scalar()
                elif dialect == 'postgresql':
                    res['details']['version'] = conn.execute(text('SHOW server_version')).scalar()

        pool = db.engine.pool
        pdata = {'type': pool.__class__.__name__}
        try:
            size, out, over = pool.size(), pool.checkedout(), pool.overflow()
            cap = size + max(0, getattr(pool, '_max_overflow', 0))
            pdata.update({'size': size, 'checked_out': out, 'overflow': over,
                          'checked_in': pool.checkedin(), 'capacity': cap,
                          'utilization_pct': round(100.0 * out / max(1, cap), 1)})
        except Exception:
            pass
        res['details']['pool'] = pdata

        res['details']['tables'] = _table_counts_cached()

        warn_ms = cfg.get('ALERT_DB_LATENCY_WARN_MS', 250)
        if res['status'] == 'ok':
            if res['latency_ms'] > warn_ms:
                res['status'] = 'warn'
                res['message'] = f"Slow database responses ({res['latency_ms']} ms per ping)."
            elif pdata.get('utilization_pct', 0) >= cfg.get('ALERT_DB_POOL_WARN_PCT', 90):
                res['status'] = 'warn'
                res['message'] = f"Connection pool {pdata['utilization_pct']}% in use."
            elif res['details'].get('connection_usage_pct', 0) >= 85:
                res['status'] = 'warn'
                res['message'] = f"Database server connections {res['details']['connection_usage_pct']}% of max."
    except Exception as exc:
        res['status'] = 'fail'
        res['message'] = f'Database unreachable: {str(exc)[:200]}'
    return res


def _table_counts_cached(ttl=120):
    now = time.time()
    if _table_counts['data'] is not None and now - _table_counts['t'] < ttl:
        return _table_counts['data']
    from models import User, Message, Group, AuditLog, LoginHistory, SystemEvent
    out = {}
    try:
        with suppress_telemetry(), independent_session() as s:
            for name, model in (('users', User), ('messages', Message), ('groups', Group),
                                ('audit_logs', AuditLog), ('login_history', LoginHistory),
                                ('system_events', SystemEvent)):
                out[name] = s.query(db.func.count(model.id)).scalar()
    except Exception as exc:
        out['error'] = str(exc)[:120]
    _table_counts.update(t=now, data=out)
    return out


def _dir_size_cached(path, ttl=300, max_files=20000):
    now = time.time()
    if _dir_size['data'] is not None and now - _dir_size['t'] < ttl:
        return _dir_size['data']
    total = files = 0
    truncated = False
    for root, _dirs, names in os.walk(path):
        for n in names:
            files += 1
            if files > max_files:
                truncated = True
                break
            try:
                total += os.path.getsize(os.path.join(root, n))
            except OSError:
                pass
        if truncated:
            break
    data = {'bytes': total, 'files': min(files, max_files), 'truncated': truncated}
    _dir_size.update(t=now, data=data)
    return data


def check_storage():
    cfg = current_app.config
    path = os.path.abspath(cfg.get('UPLOAD_FOLDER', 'uploads'))
    res = {'status': 'ok', 'details': {'path': path}}
    try:
        exists = os.path.isdir(path)
        res['details']['exists'] = exists
        probe = path if exists else (os.path.dirname(path) or '.')
        res['details']['writable'] = os.access(probe, os.W_OK)
        usage = shutil.disk_usage(probe)
        free_pct = round(100.0 * usage.free / usage.total, 1)
        res['details'].update({'disk_total_gb': round(usage.total / 1024 ** 3, 1),
                               'disk_free_gb': round(usage.free / 1024 ** 3, 1), 'disk_free_pct': free_pct})
        if exists:
            res['details']['uploads'] = _dir_size_cached(path)
        if not res['details']['writable']:
            res['status'] = 'fail'
            res['message'] = 'Upload directory is not writable.'
        elif free_pct < cfg.get('ALERT_DISK_FREE_CRIT_PCT', 5):
            res['status'] = 'fail'
            res['message'] = f'Disk almost full ({free_pct}% free).'
        elif free_pct < cfg.get('ALERT_DISK_FREE_WARN_PCT', 15):
            res['status'] = 'warn'
            res['message'] = f'Disk space low ({free_pct}% free).'
    except Exception as exc:
        res.update(status='fail', message=f'Storage check failed: {str(exc)[:150]}')
    return res


def check_encryption():
    res = {'status': 'ok', 'details': {}}
    t0 = time.perf_counter()
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        aes = AESGCM(key)
        blob = aes.encrypt(nonce, b'health-check', b'aad')
        if aes.decrypt(nonce, blob, b'aad') != b'health-check':
            raise ValueError('AES-GCM round-trip mismatch')
        res['details']['aes_256_gcm'] = 'round-trip ok'
        res['details']['rsa_key_size'] = current_app.config.get('RSA_KEY_SIZE')
        res['details']['pbkdf2_iterations'] = current_app.config.get('PBKDF2_ITERATIONS')
    except Exception as exc:
        res.update(status='fail', message=f'Cryptography self-test failed: {str(exc)[:150]}')
    res['latency_ms'] = _ms(t0)
    return res


def check_scheduler():
    res = {'status': 'ok', 'details': {}}
    try:
        from services import cleanup_service
        sch = cleanup_service._scheduler
        if sch is None:
            res.update(status='unknown', message='Background scheduler not started in this process.')
        else:
            res['details']['running'] = bool(sch.running)
            res['details']['jobs'] = [
                {'id': j.id, 'next_run': j.next_run_time.isoformat() if j.next_run_time else None}
                for j in sch.get_jobs()]
            if not sch.running:
                res.update(status='fail', message='Disappearing-message cleanup scheduler is not running.')
    except Exception as exc:
        res.update(status='warn', message=str(exc)[:150])
    return res


def check_realtime():
    res = {'status': 'ok', 'details': {}}
    try:
        from socket_events.presence_events import _socket_users
        from models import User
        sockets = len(_socket_users)
        users = len(set(_socket_users.values()))
        with suppress_telemetry(), independent_session() as s:
            db_online = s.query(db.func.count(User.id)).filter(User.online_status == 'online').scalar()
        res['details'].update({'socket_connections': sockets, 'connected_users': users,
                               'users_marked_online': db_online})
        if db_online > users + 5:
            res['status'] = 'warn'
            res['message'] = (f'{db_online} users are marked online but only {users} have a live socket; '
                              'some disconnects may not have been processed.')
    except Exception as exc:
        res.update(status='warn', message=str(exc)[:150])
    return res


def check_process():
    res = {'status': 'ok', 'details': {
        'pid': os.getpid(), 'python': platform.python_version(), 'platform': platform.platform(),
        'uptime_seconds': telemetry.uptime_seconds, 'threads': threading.active_count(),
        'started_at': iso(telemetry.started_at)}}
    cfg = current_app.config
    try:
        import psutil
        p = psutil.Process()
        mem = psutil.virtual_memory()
        res['details'].update({
            'rss_mb': round(p.memory_info().rss / 1024 / 1024, 1),
            'cpu_percent': psutil.cpu_percent(interval=None),
            'system_memory_pct': mem.percent,
            'open_files': len(p.open_files()) if hasattr(p, 'open_files') else None})
        if mem.percent >= cfg.get('ALERT_MEMORY_WARN_PCT', 85):
            res.update(status='warn', message=f'System memory {mem.percent}% used.')
    except ImportError:
        res['details']['note'] = 'Install psutil for CPU and memory metrics.'
    except Exception as exc:
        res['details']['psutil_error'] = str(exc)[:100]
    try:
        res['details']['load_avg'] = [round(x, 2) for x in os.getloadavg()]
    except (AttributeError, OSError):
        pass
    return res


def check_configuration():
    cfg = current_app.config
    findings = []
    env = os.environ.get('FLASK_ENV', 'development')
    if cfg.get('SECRET_KEY') == 'dev-secret-key-change-in-production':
        findings.append('SECRET_KEY is the built-in default.')
    if cfg.get('JWT_SECRET_KEY') == 'jwt-secret-key-change-in-production':
        findings.append('JWT_SECRET_KEY is the built-in default.')
    if env == 'production' and cfg.get('DEBUG'):
        findings.append('DEBUG is enabled in production.')
    if env == 'production' and not cfg.get('JWT_COOKIE_SECURE'):
        findings.append('JWT cookies are not marked Secure in production.')
    details = {
        'environment': env,
        'debug': bool(cfg.get('DEBUG')),
        'rate_limiting': bool(cfg.get('RATELIMIT_ENABLED', True)),
        'email_configured': bool(cfg.get('MAIL_USERNAME')),
        'push_configured': bool(cfg.get('VAPID_PUBLIC_KEY') and cfg.get('VAPID_PRIVATE_KEY')),
        'alert_webhook': bool(cfg.get('ALERT_WEBHOOK_URL')),
        'alert_emails': len(cfg.get('ALERT_EMAILS') or []),
        'trust_proxy_headers': bool(cfg.get('TRUST_PROXY_HEADERS')),
        'findings': findings,
    }
    return {'status': 'warn' if findings else 'ok', 'details': details,
            'message': '; '.join(findings) if findings else None}


CHECKS = (('database', check_database), ('storage', check_storage), ('encryption', check_encryption),
          ('scheduler', check_scheduler), ('realtime', check_realtime), ('process', check_process),
          ('configuration', check_configuration))


def run_health_checks(force=False, ttl=10):
    with _cache_lock:
        if not force and _cache['data'] and time.time() - _cache['t'] < ttl:
            return _cache['data']
        t0 = time.perf_counter()
        checks = {}
        for name, fn in CHECKS:
            started = time.perf_counter()
            try:
                checks[name] = fn()
            except Exception as exc:
                checks[name] = {'status': 'fail', 'message': f'Check crashed: {exc}', 'details': {}}
            checks[name]['duration_ms'] = _ms(started)

        statuses = [c['status'] for c in checks.values()]
        if checks['database']['status'] == 'fail':
            overall = 'down'
        elif 'fail' in statuses:
            overall = 'degraded'
        elif 'warn' in statuses:
            overall = 'degraded'
        else:
            overall = 'ok'
        data = {'status': overall, 'checked_at': iso(time.time()), 'duration_ms': _ms(t0), 'checks': checks}
        _cache.update(t=time.time(), data=data)

    # Record state *changes* (not every probe) so history shows when things broke/recovered.
    for name, c in checks.items():
        prev = _last_status.get(name)
        if prev is not None and prev != c['status']:
            worse = c['status'] in ('fail', 'warn') and prev == 'ok'
            record_event('ERROR' if c['status'] == 'fail' else ('WARNING' if worse else 'INFO'),
                         'system', f'health_{name}_{c["status"]}',
                         f'{name} check changed from {prev} to {c["status"]}'
                         + (f': {c.get("message")}' if c.get('message') else ''), details=c.get('details'))
            logger.log(logging.ERROR if c['status'] == 'fail' else logging.WARNING if worse else logging.INFO,
                       'Health check "%s": %s -> %s %s', name, prev, c['status'], c.get('message') or '')
        _last_status[name] = c['status']
    return data


# ==================================================================== rules
def _failed_logins(minutes):
    from models import LoginHistory
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    with suppress_telemetry(), independent_session() as s:
        rows = s.query(LoginHistory.ip_address, LoginHistory.identifier, LoginHistory.failure_code) \
            .filter(LoginHistory.success == False, LoginHistory.login_time >= cutoff).all()  # noqa: E712
    return rows


def evaluate_rules(health=None):
    """Return the list of conditions currently firing."""
    cfg = current_app.config
    health = health or run_health_checks(force=True)
    firing = []

    def fire(rule, severity, fp, title, message, details=None):
        firing.append({'rule': rule, 'severity': severity, 'fingerprint': fp, 'title': title,
                       'message': message, 'details': details})

    # -- database / infrastructure ------------------------------------------
    db_check = health['checks']['database']
    if db_check['status'] == 'fail':
        fire('database', 'critical', 'database:down', 'Database is unavailable', db_check.get('message'))
    elif db_check['status'] == 'warn':
        fire('database', 'warning', 'database:degraded', 'Database is degraded', db_check.get('message'),
             db_check.get('details', {}).get('pool'))

    st = health['checks']['storage']
    if st['status'] == 'fail':
        fire('storage', 'critical', 'storage:problem', 'Storage problem', st.get('message'), st['details'])
    elif st['status'] == 'warn':
        fire('storage', 'warning', 'storage:low', 'Disk space is low', st.get('message'), st['details'])

    if health['checks']['scheduler']['status'] == 'fail':
        fire('scheduler', 'warning', 'scheduler:stopped', 'Background scheduler stopped',
             health['checks']['scheduler'].get('message'))
    if health['checks']['encryption']['status'] == 'fail':
        fire('encryption', 'critical', 'encryption:selftest', 'Encryption self-test failed',
             health['checks']['encryption'].get('message'))
    if health['checks']['process']['status'] == 'warn':
        fire('resources', 'warning', 'resources:memory', 'High memory usage',
             health['checks']['process'].get('message'))

    # -- HTTP behaviour (last 5 minutes) ------------------------------------
    s5 = telemetry.summary(5)
    if s5['requests'] >= cfg.get('ALERT_MIN_REQUESTS', 20):
        er = s5['error_rate']
        if er >= cfg.get('ALERT_ERROR_RATE_CRIT', 15):
            fire('error_rate', 'critical', 'http:error_rate', 'Very high server error rate',
                 f"{er}% of requests failed with 5xx in the last 5 minutes ({s5['errors_5xx']}/{s5['requests']}).", s5)
        elif er >= cfg.get('ALERT_ERROR_RATE_WARN', 5):
            fire('error_rate', 'warning', 'http:error_rate', 'Elevated server error rate',
                 f"{er}% of requests failed with 5xx in the last 5 minutes ({s5['errors_5xx']}/{s5['requests']}).", s5)
        p95 = s5['p95_ms'] or 0
        if p95 >= cfg.get('ALERT_P95_CRIT_MS', 4000):
            fire('latency', 'critical', 'http:latency', 'Responses are very slow',
                 f'95th percentile response time is {p95:.0f} ms over the last 5 minutes.', s5)
        elif p95 >= cfg.get('ALERT_P95_WARN_MS', 1500):
            fire('latency', 'warning', 'http:latency', 'Responses are slow',
                 f'95th percentile response time is {p95:.0f} ms over the last 5 minutes.', s5)
    if s5['slow_queries'] >= cfg.get('ALERT_SLOW_QUERY_BURST', 10):
        fire('slow_queries', 'warning', 'db:slow_queries', 'Burst of slow database queries',
             f"{s5['slow_queries']} queries took over {cfg.get('SLOW_QUERY_MS', 500)} ms in the last 5 minutes.",
             {'recent': telemetry.get_slow_queries(3)})

    # -- authentication attacks ---------------------------------------------
    window = cfg.get('ALERT_FAILED_LOGIN_WINDOW_MIN', 10)
    try:
        rows = _failed_logins(window)
    except Exception as exc:
        rows = []
        logger.debug('failed-login rule skipped: %s', exc)
    if rows:
        total = len(rows)
        if total >= cfg.get('ALERT_FAILED_LOGIN_TOTAL', 15):
            fire('failed_logins', 'warning', 'auth:failed_login_spike', 'Spike in failed logins',
                 f'{total} failed login attempts in the last {window} minutes.', {'total': total})
        per_ip, idents_per_ip, per_ident = {}, {}, {}
        for ip, ident, code in rows:
            if ip:
                per_ip[ip] = per_ip.get(ip, 0) + 1
                if ident:
                    idents_per_ip.setdefault(ip, set()).add(ident.lower())
            if ident and code in ('invalid_password', 'user_not_found'):
                per_ident[ident.lower()] = per_ident.get(ident.lower(), 0) + 1
        for ip, n in per_ip.items():
            if n >= cfg.get('ALERT_FAILED_LOGIN_PER_IP', 8):
                fire('brute_force', 'critical', f'auth:brute_force:{ip}', f'Possible brute-force from {ip}',
                     f'{n} failed logins from {ip} in the last {window} minutes.', {'ip': ip, 'attempts': n})
        for ip, idents in idents_per_ip.items():
            if len(idents) >= cfg.get('ALERT_DISTINCT_IDENTIFIERS_PER_IP', 5):
                fire('credential_stuffing', 'critical', f'auth:stuffing:{ip}',
                     f'Possible credential stuffing from {ip}',
                     f'{ip} tried {len(idents)} different accounts in the last {window} minutes.',
                     {'ip': ip, 'accounts': sorted(idents)[:10]})
        max_attempts = cfg.get('MAX_LOGIN_ATTEMPTS', 5)
        for ident, n in per_ident.items():
            if n >= max_attempts:
                fire('account_lockout', 'warning', f'auth:locked:{ident}', f'Account "{ident}" is locked out',
                     f'{n} failed password attempts for "{ident}" in the last {window} minutes.',
                     {'identifier': ident, 'attempts': n})
    return firing


def run_evaluation(app=None):
    """One monitoring cycle: probe, evaluate, raise and auto-resolve alerts."""
    app = app or current_app._get_current_object()
    with app.app_context():
        try:
            health = run_health_checks(force=True)
            firing = evaluate_rules(health)
            seen = set()
            for f in firing:
                seen.add(f['fingerprint'])
                _ok_streak.pop(f['fingerprint'], None)
                alert_service.raise_alert(f['rule'], f['severity'], f['title'], f['message'],
                                          fingerprint=f['fingerprint'], details=f['details'])

            # Condition alerts clear themselves after two consecutive clean cycles.
            auto_rules = {'database', 'storage', 'scheduler', 'encryption', 'resources', 'error_rate',
                          'latency', 'slow_queries', 'failed_logins', 'brute_force', 'credential_stuffing',
                          'account_lockout'}
            for a in alert_service.open_alerts():
                if a['rule'] in auto_rules and a['fingerprint'] not in seen:
                    n = _ok_streak.get(a['fingerprint'], 0) + 1
                    _ok_streak[a['fingerprint']] = n
                    if n >= 2:
                        alert_service.resolve_alert(a['fingerprint'], by='auto')
                        _ok_streak.pop(a['fingerprint'], None)
                elif a['rule'] not in auto_rules:
                    # Event alerts (exceptions, admin actions) expire after an hour without recurrence.
                    last = datetime.fromisoformat(a['last_seen'].rstrip('Z'))
                    if datetime.utcnow() - last > timedelta(hours=1) and a['status'] != 'open':
                        alert_service.resolve_alert(a['fingerprint'], by='auto')
        except Exception as exc:
            logger.error('Monitoring cycle failed: %s', exc, exc_info=True)


_cycles = {'n': 0}


def _tick(app):
    run_evaluation(app)
    _cycles['n'] += 1
    # Retention once an hour (every N cycles).
    per_hour = max(1, int(3600 / max(1, app.config.get('MONITOR_INTERVAL_SECONDS', 30))))
    if _cycles['n'] % per_hour == 1:
        with app.app_context():
            purge_old_records(app.config.get('EVENT_RETENTION_DAYS', 30))


def start_monitoring(app):
    """Start the evaluator once per process (honours the debug reloader)."""
    global _scheduler
    if _scheduler is not None or not app.config.get('MONITOR_ENABLED', True) or app.config.get('TESTING'):
        return
    if app.config.get('DEBUG') and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(lambda: _tick(app), 'interval',
                       seconds=app.config.get('MONITOR_INTERVAL_SECONDS', 30),
                       id='monitoring_cycle', replace_existing=True, max_instances=1, coalesce=True,
                       next_run_time=datetime.now() + timedelta(seconds=5))
    _scheduler.start()
    logger.info('Monitoring started (every %ss)', app.config.get('MONITOR_INTERVAL_SECONDS', 30))


# ====================================================== rule catalogue (UI)
def rule_catalogue():
    c = current_app.config
    return [
        {'rule': 'database', 'title': 'Database health', 'severity': 'critical / warning',
         'description': f"Database unreachable or read-only (critical); ping over {c['ALERT_DB_LATENCY_WARN_MS']} ms "
                        f"or pool over {c['ALERT_DB_POOL_WARN_PCT']}% used (warning)."},
        {'rule': 'error_rate', 'title': 'Server error rate', 'severity': 'critical / warning',
         'description': f"5xx responses over {c['ALERT_ERROR_RATE_WARN']}% (warning) or {c['ALERT_ERROR_RATE_CRIT']}% "
                        f"(critical) of the last 5 minutes, with at least {c['ALERT_MIN_REQUESTS']} requests."},
        {'rule': 'latency', 'title': 'Response time (p95)', 'severity': 'critical / warning',
         'description': f"95th percentile over {c['ALERT_P95_WARN_MS']} ms (warning) or {c['ALERT_P95_CRIT_MS']} ms "
                        f"(critical) across the last 5 minutes."},
        {'rule': 'slow_queries', 'title': 'Slow queries', 'severity': 'warning',
         'description': f"{c['ALERT_SLOW_QUERY_BURST']} or more queries slower than {c['SLOW_QUERY_MS']} ms in 5 minutes."},
        {'rule': 'failed_logins', 'title': 'Failed-login spike', 'severity': 'warning',
         'description': f"{c['ALERT_FAILED_LOGIN_TOTAL']} or more failed logins in {c['ALERT_FAILED_LOGIN_WINDOW_MIN']} minutes."},
        {'rule': 'brute_force', 'title': 'Brute-force from one IP', 'severity': 'critical',
         'description': f"{c['ALERT_FAILED_LOGIN_PER_IP']} or more failed logins from a single IP address."},
        {'rule': 'credential_stuffing', 'title': 'Credential stuffing', 'severity': 'critical',
         'description': f"One IP trying {c['ALERT_DISTINCT_IDENTIFIERS_PER_IP']} or more different accounts."},
        {'rule': 'account_lockout', 'title': 'Account lockout', 'severity': 'warning',
         'description': f"An account reaches {c['MAX_LOGIN_ATTEMPTS']} failed passwords "
                        f"(locked for {c['LOCKOUT_TIME']} minutes)."},
        {'rule': 'storage', 'title': 'Disk & uploads', 'severity': 'critical / warning',
         'description': f"Free disk under {c['ALERT_DISK_FREE_WARN_PCT']}% (warning) or {c['ALERT_DISK_FREE_CRIT_PCT']}% "
                        f"(critical), or uploads folder not writable."},
        {'rule': 'scheduler', 'title': 'Background jobs', 'severity': 'warning',
         'description': 'The disappearing-message cleanup scheduler stopped.'},
        {'rule': 'encryption', 'title': 'Encryption self-test', 'severity': 'critical',
         'description': 'The AES-GCM round-trip self-test failed.'},
        {'rule': 'resources', 'title': 'Memory', 'severity': 'warning',
         'description': f"System memory over {c['ALERT_MEMORY_WARN_PCT']}% (needs psutil)."},
        {'rule': 'unhandled_exception', 'title': 'Unhandled exceptions', 'severity': 'critical',
         'description': 'Raised immediately when a request crashes with an unexpected error.'},
        {'rule': 'admin_change', 'title': 'Sensitive admin actions', 'severity': 'warning',
         'description': 'Admin rights granted/revoked, accounts deleted, or non-admins probing admin endpoints.'},
    ]
