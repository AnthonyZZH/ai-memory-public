"""Process-lifetime advisory lock. The lock file is retained, never deleted."""
from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path


@contextmanager
def acquire(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('processor_busy') from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def exclusive(function):
    @wraps(function)
    def wrapped(config, *args, **kwargs):
        path = config.resolve(config.data['cursor_db']).with_suffix('.mutex')
        with acquire(path):
            return function(config, *args, **kwargs)
    return wrapped
