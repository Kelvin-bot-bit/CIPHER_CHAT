# backend/utils/schema_upgrade.py
"""
Idempotent schema upgrade for the monitoring / audit improvements.

The project creates some tables at start-up instead of requiring a manual
migration step (see create_app), so the new columns and tables are brought up
to date the same way: safe to run on every start, a no-op once applied. The
matching Alembic migration calls the same function.

Changes:
  * new tables ``system_events`` and ``alerts``
  * login_history: user_id becomes NULLable (failed logins for unknown
    usernames have no user), plus identifier / failure_code / request_id
  * audit_logs: actor_username / actor_email / resource_label / request_id
  * back-fills the new columns for existing rows
"""
import logging

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

NEW_COLUMNS = {
    'login_history': [
        ('identifier', 'VARCHAR(255)'),
        ('failure_code', 'VARCHAR(40)'),
        ('request_id', 'VARCHAR(36)'),
    ],
    'audit_logs': [
        ('actor_username', 'VARCHAR(100)'),
        ('actor_email', 'VARCHAR(255)'),
        ('resource_label', 'VARCHAR(255)'),
        ('request_id', 'VARCHAR(36)'),
    ],
}

NEW_INDEXES = [
    ('login_history', 'idx_login_identifier', 'identifier'),
    ('login_history', 'idx_login_ip', 'ip_address'),
]


def _exec(bind, sql, what):
    try:
        bind.execute(text(sql))
        return True
    except Exception as exc:
        logger.warning('Schema upgrade step skipped (%s): %s', what, str(exc).splitlines()[0][:160])
        return False


def apply_schema_upgrades(bind):
    """``bind`` is an Engine or a Connection."""
    from extensions import db
    from models.monitoring import SystemEvent, Alert

    from sqlalchemy.engine import Engine
    is_engine = isinstance(bind, Engine)

    def run(fn):
        # Engines: one short transaction per step. Alembic hands us a
        # Connection that is already inside its migration transaction.
        if is_engine:
            with bind.begin() as conn:
                fn(conn)
        else:
            fn(bind)

    # 1. New tables
    for table in (SystemEvent.__table__, Alert.__table__):
        try:
            table.create(bind=bind, checkfirst=True)
        except Exception as exc:
            logger.warning('Could not create %s: %s', table.name, exc)

    insp = inspect(bind)
    tables = set(insp.get_table_names())
    dialect = bind.dialect.name

    # 2. New columns
    for table, cols in NEW_COLUMNS.items():
        if table not in tables:
            continue
        existing = {c['name'] for c in insp.get_columns(table)}
        for name, ddl in cols:
            if name not in existing:
                run(lambda c, t=table, n=name, d=ddl: _exec(c, f'ALTER TABLE {t} ADD COLUMN {n} {d}', f'{t}.{n}'))

    # 3. login_history.user_id must allow NULL
    if 'login_history' in tables:
        for col in insp.get_columns('login_history'):
            if col['name'] == 'user_id' and not col.get('nullable', True):
                if dialect == 'mysql':
                    run(lambda c: _exec(c, 'ALTER TABLE login_history MODIFY user_id INT NULL', 'user_id nullable'))
                elif dialect == 'postgresql':
                    run(lambda c: _exec(c, 'ALTER TABLE login_history ALTER COLUMN user_id DROP NOT NULL',
                                        'user_id nullable'))
                else:
                    logger.warning('login_history.user_id is NOT NULL and %s cannot alter it in place; '
                                   'failed logins for unknown usernames cannot be stored with a user id.', dialect)

    # 4. Indexes
    insp = inspect(bind)
    for table, name, col in NEW_INDEXES:
        if table in tables:
            have = {i['name'] for i in insp.get_indexes(table)}
            if name not in have:
                run(lambda c, t=table, n=name, cl=col: _exec(c, f'CREATE INDEX {n} ON {t} ({cl})', n))

    # 5. Back-fill (only touches rows that lack the new data)
    if 'audit_logs' in tables:
        run(lambda c: _exec(c, 'UPDATE audit_logs SET actor_username = '
                               '(SELECT u.username FROM users u WHERE u.id = audit_logs.user_id) '
                               'WHERE actor_username IS NULL AND user_id IS NOT NULL', 'backfill audit username'))
        run(lambda c: _exec(c, 'UPDATE audit_logs SET actor_email = '
                               '(SELECT u.email FROM users u WHERE u.id = audit_logs.user_id) '
                               'WHERE actor_email IS NULL AND user_id IS NOT NULL', 'backfill audit email'))
    if 'login_history' in tables:
        run(lambda c: _exec(c, 'UPDATE login_history SET identifier = '
                               '(SELECT u.username FROM users u WHERE u.id = login_history.user_id) '
                               'WHERE identifier IS NULL AND user_id IS NOT NULL', 'backfill login identifier'))
        run(lambda c: _exec(c, "UPDATE login_history SET failure_code = 'invalid_password' "
                               "WHERE failure_code IS NULL AND success = 0 AND failure_reason = 'Invalid password'",
                            'backfill failure_code'))
        run(lambda c: _exec(c, "UPDATE login_history SET failure_code = 'user_not_found' "
                               "WHERE failure_code IS NULL AND success = 0 AND failure_reason = 'User not found'",
                            'backfill failure_code'))


def ensure_observability_schema(app):
    with app.app_context():
        try:
            from extensions import db
            apply_schema_upgrades(db.engine)
        except Exception as exc:
            app.logger.error('Observability schema upgrade failed: %s', exc)
