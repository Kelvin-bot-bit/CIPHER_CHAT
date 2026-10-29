# backend/services/telemetry.py
"""
In-process telemetry store.

Keeps bounded, thread-safe, in-memory views of what the server is doing right
now so the admin dashboard can answer "what is happening?" without a metrics
stack:

* a ring buffer of recent HTTP requests (with timing, status, user, db cost)
* a ring buffer of recent structured log records
* per-minute buckets (24h) of request counts, error counts and latency
  samples for the time-series charts and percentile maths
* slow database queries

Everything here is per-process and resets on restart. Anything that must
survive a restart (errors, alerts, audit trail) is persisted separately in
the database, and every request/log line is also written to rotating files.
"""
import random
import threading
import time
from collections import deque
from datetime import datetime, timezone

BUCKET_SECONDS = 60
MAX_BUCKETS = 24 * 60          # 24h of 1-minute buckets
SAMPLES_PER_BUCKET = 100       # reservoir size for latency percentiles


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def percentile(sorted_values, p):
    """Nearest-rank-with-interpolation percentile of an already sorted list."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


class _Bucket:
    __slots__ = ('t', 'n', 'e5', 'e4', 'sum_ms', 'max_ms', 'samples', 'db_n', 'db_ms',
                 'slow_q', 'slow_r', 'bytes')

    def __init__(self, t):
        self.t = t
        self.n = 0
        self.e5 = 0
        self.e4 = 0
        self.sum_ms = 0.0
        self.max_ms = 0.0
        self.samples = []
        self.db_n = 0
        self.db_ms = 0.0
        self.slow_q = 0
        self.slow_r = 0
        self.bytes = 0


class Telemetry:
    def __init__(self, request_ring=10000, log_ring=5000):
        self.lock = threading.RLock()
        self.started_at = time.time()
        self.requests = deque(maxlen=request_ring)
        self.logs = deque(maxlen=log_ring)
        self.slow_queries = deque(maxlen=200)
        self.buckets = {}
        self._req_seq = 0
        self._log_seq = 0
        self.db_queries_total = 0
        self.db_errors_total = 0
        self.requests_total = 0
        self.errors_5xx_total = 0
        # Set by code that runs its own housekeeping queries so they are not
        # counted as application load.
        self.suppress = threading.local()

    # ------------------------------------------------------------ config
    def configure(self, request_ring=None, log_ring=None):
        with self.lock:
            if request_ring and request_ring != self.requests.maxlen:
                self.requests = deque(self.requests, maxlen=request_ring)
            if log_ring and log_ring != self.logs.maxlen:
                self.logs = deque(self.logs, maxlen=log_ring)

    # ----------------------------------------------------------- helpers
    def _bucket(self, now):
        t = int(now // BUCKET_SECONDS) * BUCKET_SECONDS
        b = self.buckets.get(t)
        if b is None:
            b = self.buckets[t] = _Bucket(t)
            if len(self.buckets) > MAX_BUCKETS:
                for old in sorted(self.buckets)[: len(self.buckets) - MAX_BUCKETS]:
                    del self.buckets[old]
        return b

    # ---------------------------------------------------------- recording
    def record_request(self, rec):
        """``rec`` is a dict; id/ts/t are filled in here."""
        now = time.time()
        with self.lock:
            self._req_seq += 1
            rec['id'] = self._req_seq
            rec['t'] = now
            rec['ts'] = iso(now)
            self.requests.append(rec)
            self.requests_total += 1

            if rec.get('internal'):
                return rec  # dashboard polling is kept for debugging but not measured
            b = self._bucket(now)
            ms = float(rec.get('ms') or 0)
            status = int(rec.get('status') or 0)
            b.n += 1
            b.sum_ms += ms
            b.max_ms = max(b.max_ms, ms)
            b.bytes += int(rec.get('bytes') or 0)
            if status >= 500:
                b.e5 += 1
                self.errors_5xx_total += 1
            elif status >= 400:
                b.e4 += 1
            if rec.get('slow'):
                b.slow_r += 1
            if len(b.samples) < SAMPLES_PER_BUCKET:
                b.samples.append(ms)
            else:
                j = random.randint(0, b.n - 1)
                if j < SAMPLES_PER_BUCKET:
                    b.samples[j] = ms
        return rec

    def record_query(self, statement, ms, slow, request_id=None):
        if getattr(self.suppress, 'on', False):
            return
        now = time.time()
        with self.lock:
            self.db_queries_total += 1
            b = self._bucket(now)
            b.db_n += 1
            b.db_ms += ms
            if slow:
                b.slow_q += 1
                self.slow_queries.append({
                    'ts': iso(now), 't': now, 'ms': round(ms, 1),
                    'statement': statement, 'request_id': request_id,
                })

    def record_query_error(self):
        if getattr(self.suppress, 'on', False):
            return
        with self.lock:
            self.db_errors_total += 1

    def record_log(self, rec):
        with self.lock:
            self._log_seq += 1
            rec['id'] = self._log_seq
            self.logs.append(rec)

    # ------------------------------------------------------------- reads
    def _window_buckets(self, minutes):
        cutoff = (time.time() // BUCKET_SECONDS) * BUCKET_SECONDS - (minutes - 1) * BUCKET_SECONDS
        return [b for t, b in sorted(self.buckets.items()) if t >= cutoff]

    def summary(self, minutes=5):
        """Aggregate request health over the last ``minutes``."""
        with self.lock:
            bs = self._window_buckets(minutes)
            n = sum(b.n for b in bs)
            e5 = sum(b.e5 for b in bs)
            e4 = sum(b.e4 for b in bs)
            total_ms = sum(b.sum_ms for b in bs)
            samples = []
            for b in bs:
                samples.extend(b.samples)
            db_n = sum(b.db_n for b in bs)
            db_ms = sum(b.db_ms for b in bs)
            slow_q = sum(b.slow_q for b in bs)
            slow_r = sum(b.slow_r for b in bs)
            max_ms = max((b.max_ms for b in bs), default=0.0)
        if len(samples) > 20000:
            samples = random.sample(samples, 20000)
        samples.sort()
        return {
            'window_minutes': minutes,
            'requests': n,
            'rps': round(n / (minutes * 60.0), 3),
            'errors_5xx': e5,
            'errors_4xx': e4,
            'error_rate': round(100.0 * e5 / n, 2) if n else 0.0,
            'client_error_rate': round(100.0 * e4 / n, 2) if n else 0.0,
            'avg_ms': round(total_ms / n, 1) if n else None,
            'p50_ms': _r(percentile(samples, 50)),
            'p95_ms': _r(percentile(samples, 95)),
            'p99_ms': _r(percentile(samples, 99)),
            'max_ms': round(max_ms, 1) if n else None,
            'slow_requests': slow_r,
            'db_queries': db_n,
            'db_avg_ms': round(db_ms / db_n, 2) if db_n else None,
            'slow_queries': slow_q,
        }

    def timeseries(self, minutes=60):
        """One point per minute, zero-filled so charts have no gaps."""
        now_bucket = int(time.time() // BUCKET_SECONDS) * BUCKET_SECONDS
        out = []
        with self.lock:
            for i in range(minutes - 1, -1, -1):
                t = now_bucket - i * BUCKET_SECONDS
                b = self.buckets.get(t)
                if b and b.n:
                    s = sorted(b.samples)
                    out.append({
                        't': iso(t), 'requests': b.n, 'errors_5xx': b.e5, 'errors_4xx': b.e4,
                        'avg_ms': round(b.sum_ms / b.n, 1), 'p95_ms': _r(percentile(s, 95)),
                        'max_ms': round(b.max_ms, 1),
                        'db_avg_ms': round(b.db_ms / b.db_n, 2) if b.db_n else None,
                        'slow_queries': b.slow_q,
                    })
                else:
                    out.append({'t': iso(t), 'requests': 0, 'errors_5xx': 0, 'errors_4xx': 0,
                                'avg_ms': None, 'p95_ms': None, 'max_ms': None,
                                'db_avg_ms': None, 'slow_queries': 0})
        return out

    def endpoint_stats(self, minutes=60, sort='p95', limit=30):
        """Per-route latency/error table, computed from the request ring."""
        cutoff = time.time() - minutes * 60
        groups = {}
        with self.lock:
            for r in self.requests:
                if r['t'] < cutoff or r.get('internal'):
                    continue
                key = f"{r['method']} {r.get('route') or '(unmatched)'}"
                g = groups.setdefault(key, {'method': r['method'], 'route': r.get('route') or '(unmatched)',
                                            'ms': [], 'e5': 0, 'e4': 0, 'last': 0, 'db_ms': 0.0, 'users': set()})
                g['ms'].append(float(r.get('ms') or 0))
                st = int(r.get('status') or 0)
                if st >= 500:
                    g['e5'] += 1
                elif st >= 400:
                    g['e4'] += 1
                g['db_ms'] += float(r.get('db_ms') or 0)
                g['last'] = max(g['last'], r['t'])
                if r.get('user_id'):
                    g['users'].add(r['user_id'])
        rows = []
        for g in groups.values():
            ms = sorted(g['ms'])
            n = len(ms)
            rows.append({
                'method': g['method'], 'route': g['route'], 'count': n,
                'errors_5xx': g['e5'], 'errors_4xx': g['e4'],
                'error_rate': round(100.0 * g['e5'] / n, 1),
                'avg_ms': round(sum(ms) / n, 1), 'p50_ms': _r(percentile(ms, 50)),
                'p95_ms': _r(percentile(ms, 95)), 'p99_ms': _r(percentile(ms, 99)),
                'max_ms': round(ms[-1], 1),
                'db_avg_ms': round(g['db_ms'] / n, 1),
                'users': len(g['users']),
                'last_seen': iso(g['last']),
            })
        keymap = {'p95': 'p95_ms', 'avg': 'avg_ms', 'count': 'count', 'errors': 'errors_5xx', 'max': 'max_ms'}
        k = keymap.get(sort, 'p95_ms')
        rows.sort(key=lambda r: (r[k] or 0), reverse=True)
        return rows[:limit]

    def status_codes(self, minutes=60):
        cutoff = time.time() - minutes * 60
        out = {}
        with self.lock:
            for r in self.requests:
                if r['t'] >= cutoff and not r.get('internal'):
                    k = str(r.get('status'))
                    out[k] = out.get(k, 0) + 1
        return out

    def get_requests(self, limit=100, since_id=None, status=None, method=None, q=None,
                     user_id=None, min_ms=None, slow=False, request_id=None, ip=None):
        limit = max(1, min(int(limit or 100), 500))
        out = []
        q = (q or '').lower()
        with self.lock:
            items = list(self.requests)
        for r in reversed(items):
            if since_id is not None and r['id'] <= since_id:
                break
            if r.get('internal') and not (q or request_id):
                continue
            st = int(r.get('status') or 0)
            if status:
                if status.endswith('xx'):
                    if st // 100 != int(status[0]):
                        continue
                elif status.isdigit() and st != int(status):
                    continue
            if method and r['method'] != method.upper():
                continue
            if user_id is not None and r.get('user_id') != user_id:
                continue
            if min_ms is not None and (r.get('ms') or 0) < min_ms:
                continue
            if slow and not r.get('slow'):
                continue
            if request_id and r.get('request_id') != request_id:
                continue
            if ip and r.get('ip') != ip:
                continue
            if q and q not in (r.get('path') or '').lower() and q not in (r.get('username') or '').lower() \
                    and q not in (r.get('route') or '').lower():
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def get_logs(self, limit=200, since_id=None, level=None, logger=None, q=None, request_id=None):
        limit = max(1, min(int(limit or 200), 1000))
        rank = {'DEBUG': 10, 'INFO': 20, 'WARNING': 30, 'ERROR': 40, 'CRITICAL': 50}
        min_rank = rank.get((level or '').upper(), 0)
        q = (q or '').lower()
        with self.lock:
            items = list(self.logs)
        out = []
        for r in reversed(items):
            if since_id is not None and r['id'] <= since_id:
                break
            if rank.get(r['level'], 0) < min_rank:
                continue
            if logger and logger.lower() not in (r.get('logger') or '').lower():
                continue
            if request_id and r.get('request_id') != request_id:
                continue
            if q and q not in (r.get('message') or '').lower() and q not in (r.get('exception') or '').lower():
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def log_level_counts(self, minutes=60):
        cutoff = time.time() - minutes * 60
        out = {'DEBUG': 0, 'INFO': 0, 'WARNING': 0, 'ERROR': 0, 'CRITICAL': 0}
        with self.lock:
            for r in self.logs:
                if r['t'] >= cutoff:
                    out[r['level']] = out.get(r['level'], 0) + 1
        return out

    def get_slow_queries(self, limit=50):
        with self.lock:
            return list(reversed(list(self.slow_queries)))[:limit]

    def recent_count(self, predicate, minutes):
        cutoff = time.time() - minutes * 60
        with self.lock:
            return sum(1 for r in self.requests if r['t'] >= cutoff and predicate(r))

    @property
    def uptime_seconds(self):
        return int(time.time() - self.started_at)


def _r(v):
    return round(v, 1) if v is not None else None


telemetry = Telemetry()
