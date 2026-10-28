"""Single-owner daily pipeline; local HTTP only, count/code-only logs."""
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import Request, ProxyHandler, build_opener

from conversation_processor.config import local_endpoint
from conversation_processor.extract import NoRedirect
from .engine import run as engine_run
from .policy import EngineError, exclusive, inside, now


def endpoint(base, suffix):
    # Reuse processor's strict loopback validation without /chat/completions.
    local_endpoint(base)
    parsed = urlsplit(base)
    if parsed.path not in ('', '/'):
        raise EngineError('daily_base_path_invalid')
    return base.rstrip('/').replace('://localhost', '://127.0.0.1') + suffix


def request(base, path, body=None):
    url = endpoint(base, path)
    data = None if body is None else json.dumps(body).encode('utf-8')
    try:
        req = Request(url, data=data, headers={'Content-Type': 'application/json'})
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=5) as response:
            raw = response.read(1048577)
        if len(raw) > 1048576:
            raise ValueError()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except Exception:
        raise EngineError('daily_local_http_unavailable') from None


def healthy(settings):
    try:
        value = request(settings['model_url'], '/health')
        return value.get('status') in ('ok', 'ready')
    except EngineError:
        return False


def counts(value, prefix=''):
    result = {}
    if isinstance(value, dict):
        for key, item in value.items():
            name = prefix + str(key)
            if type(item) is int:
                result[name] = item
            elif isinstance(item, dict):
                result.update(counts(item, name + '.'))
    return result


def log(config, event, code, values=None):
    path = config.root / 'cache/xq-daily.log'
    if not inside(path, config.root / 'cache') or not inside(path, config.root):
        raise EngineError('daily_log_path_invalid')
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {'time': now(), 'event': event, 'code': code, 'counts': counts(values or {})}
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + '\n')


def runtime_pin(settings, profile):
    if not isinstance(profile, str) or re.fullmatch(r'[A-Za-z0-9_-]+', profile) is None:
        raise EngineError('daily_profile_invalid')
    directory = Path(settings['runtime_directory']).resolve()
    path = directory / (profile + '.json')
    if not inside(path, directory):
        raise EngineError('daily_runtime_path_invalid')
    if not path.exists():
        return None
    # Hash the opaque record; never print or store its token-bearing contents.
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_ino, hashlib.sha256(path.read_bytes()).hexdigest())


def run(config, dry_run=False):
    settings = config.data['daily']
    endpoint(settings['model_url'], '/health')
    endpoint(settings['control_url'], '/model/status')
    if dry_run:
        return {'dry_run': True, 'code': 'preview', 'steps': ['check_model', 'start_if_stopped', 'collect', 'extract', 'reflect', 'apply', 'sync_if_changed', 'restore_if_owned']}
    result = {'code': 'ok', 'phases': {}, 'started': 0, 'stopped': 0}
    owned_profile, pin, start_accepted = None, None, False
    with exclusive(config):
        try:
            if not healthy(settings):
                initial = request(settings['control_url'], '/model/status')
                state = initial.get('state')
                if state == 'stopped':
                    profile = initial['selected']
                    if runtime_pin(settings, profile) is not None:
                        raise EngineError('daily_existing_runtime_record')
                    # Recheck health immediately before asking the launcher.
                    if not healthy(settings):
                        response = request(settings['control_url'], '/model/start', {'profile': profile})
                        if response.get('state') == 'starting' and response.get('job_profile') == profile:
                            owned_profile, start_accepted = profile, True
                            result['started'] = 1
                        elif response.get('state') != 'ready':
                            raise EngineError('daily_start_not_owned')
                elif state not in ('starting', 'ready'):
                    raise EngineError('daily_model_control_busy')
                deadline = time.monotonic() + settings['start_timeout_seconds']
                while not healthy(settings):
                    if start_accepted and pin is None:
                        pin = runtime_pin(settings, owned_profile)
                    if time.monotonic() >= deadline:
                        raise EngineError('daily_start_timeout')
                    status = request(settings['control_url'], '/model/status')
                    if status.get('error') or status.get('state') == 'stopped':
                        raise EngineError('daily_start_failed')
                    time.sleep(settings['poll_seconds'])
                if start_accepted:
                    pin = pin or runtime_pin(settings, owned_profile)
                    if pin is None:
                        raise EngineError('daily_ownership_unconfirmed')
            for phase in ('collect', 'extract', 'reflect', 'apply'):
                values = engine_run(config, phase)
                result['phases'][phase] = counts(values)
                log(config, phase, 'ok', values)
        except Exception as exc:
            code = str(exc) if isinstance(exc, EngineError) and re.fullmatch('[a-z0-9_]+', str(exc)) else 'daily_pipeline_failed'
            result['code'] = code
            log(config, 'pipeline', code)
        finally:
            # Reconcile snapshots even after a partial pipeline failure. sync
            # computes changes and is a zero-write operation when already current.
            try:
                values = engine_run(config, 'sync')
                result['phases']['sync'] = counts(values)
                log(config, 'sync', 'ok', values)
            except Exception:
                log(config, 'sync', 'daily_sync_failed')
                if result['code'] == 'ok':
                    result['code'] = 'daily_sync_failed'
            if start_accepted:
                try:
                    pin = pin or runtime_pin(settings, owned_profile)
                    current = request(settings['control_url'], '/model/status')
                    if (pin is None or runtime_pin(settings, owned_profile) != pin
                            or current.get('state') not in ('ready', 'starting')
                            or current.get('running') not in (None, owned_profile)
                            or current.get('selected') != owned_profile):
                        raise EngineError('daily_model_ownership_changed')
                    request(settings['control_url'], '/model/stop', {})
                    deadline = time.monotonic() + settings['stop_timeout_seconds']
                    while True:
                        status = request(settings['control_url'], '/model/status')
                        if status.get('state') == 'stopped' and not healthy(settings):
                            break
                        if status.get('error') or time.monotonic() >= deadline:
                            raise EngineError('daily_stop_failed')
                        time.sleep(settings['poll_seconds'])
                    result['stopped'] = 1
                    log(config, 'restore', 'ok', {'stopped': 1})
                except Exception:
                    log(config, 'restore', 'daily_restore_failed')
                    if result['code'] == 'ok':
                        result['code'] = 'daily_restore_failed'
            log(config, 'finished', result['code'], result)
    return result
