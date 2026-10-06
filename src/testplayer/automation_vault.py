"""Session-only environment values. Secret entries never leave through listing APIs."""
from __future__ import annotations

import re
import threading


class AutomationVault:
    def __init__(self):
        self._lock = threading.RLock()
        self._values = {
            'PLAYWRIGHT_EMAIL': {'value': '', 'secret': False},
            'PLAYWRIGHT_PASSWORD': {'value': '', 'secret': True},
        }

    def save(self, key: str, value: str | None, secret: bool):
        reserved = {'PATH', 'HOME', 'APPDATA', 'SYSTEMROOT', 'COMSPEC', 'TEMP', 'TMP', 'PLAYWRIGHT_BROWSERS_PATH', 'PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD'}
        if not isinstance(key, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', key) or key in reserved or key.startswith(('NODE_', 'RECORDER_', 'PYTHON')):
            raise ValueError('Use uma chave de ambiente válida, como API_TOKEN. Chaves do runtime são reservadas.')
        if not isinstance(secret, bool) or (value is not None and (not isinstance(value, str) or len(value) > 8192 or '\0' in value)):
            raise ValueError('Valor ou tipo inválido para o Cofre.')
        with self._lock:
            previous = self._values.get(key, {'value': ''})
            self._values[key] = {'value': previous['value'] if value is None else value, 'secret': secret}

    def entries(self):
        with self._lock:
            return [{'key': key, 'secret': entry['secret'], 'has_value': bool(entry['value']),
                     **({} if entry['secret'] else {'value': entry['value']})}
                    for key, entry in self._values.items()]

    def environment(self):
        with self._lock:
            return {key: entry['value'] for key, entry in self._values.items()}

    def remove(self, key):
        if not isinstance(key, str):
            raise ValueError('Chave inválida.')
        with self._lock:
            if key in ('PLAYWRIGHT_EMAIL', 'PLAYWRIGHT_PASSWORD'):
                self._values[key]['value'] = ''
            else:
                self._values.pop(key, None)

    def clear(self):
        with self._lock:
            self._values.clear()
