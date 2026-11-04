"""One reentrant coordinator per resolved data root, including journal recovery."""
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import logging
import threading

from .bugs_store import BugsStore

log = logging.getLogger(__name__)
_registry_lock = threading.Lock()
_locks = {}
_local = threading.local()


class StateConflict(ValueError):
    pass


class RecoveryPending(RuntimeError):
    def __init__(self, operation_id):
        self.operation_id = operation_id
        super().__init__(f'Operação {operation_id} aguarda recuperação. Tente novamente.')


def root_for(directory):
    directory = Path(directory).resolve()
    if directory.parent.name in ('rascunhos', 'excluidas'):
        return directory.parent.parent
    if directory.parent.parent.name == 'sessoes':
        return directory.parent.parent.parent
    # Standalone session fixtures also use the same serialization boundary.
    return directory.parent


@contextmanager
def coordinated(root):
    root = Path(root).resolve()
    key = str(root).casefold()
    with _registry_lock:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        entered = getattr(_local, 'entered', set())
        if key in entered:
            yield
            return
        _local.entered = entered | {key}
        try:
            store = BugsStore(root)
            store.initialize()
            from .bugs_service import recover_operations
            recover_operations(root, store)
            yield
        finally:
            _local.entered = entered


def session_operation(function):
    @wraps(function)
    def wrapped(directory, *args, **kwargs):
        with coordinated(root_for(directory)):
            return function(directory, *args, **kwargs)
    return wrapped


def root_operation(function):
    @wraps(function)
    def wrapped(root, *args, **kwargs):
        with coordinated(root):
            return function(root, *args, **kwargs)
    return wrapped
