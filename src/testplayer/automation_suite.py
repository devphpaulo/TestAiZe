"""Run saved spec snapshots using the Playwright installation detected at startup."""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import threading
from .automation_environment import recorder_root

_PLAYWRIGHT_LAUNCHER = (
    "const { dirname, join } = require('node:path');"
    "const entry = process.env.RECORDER_PLAYWRIGHT_MODULE;"
    "const config = process.env.TESTAIZE_SUITE_CONFIG;"
    "if (!entry || !config) process.exit(1);"
    "const cli = join(dirname(entry), 'cli.js');"
    "process.argv = [process.execPath, cli, 'test', '--config', config];"
    "process.stdin.resume();"
    "process.stdin.once('end', () => process.exit(1));"
    "require(cli);"
)


class AutomationSuiteRunner:
    def __init__(self, library, runtime, timeout=300):
        self.library = library
        self.runtime = runtime
        self.timeout = timeout
        self._lock = threading.RLock()
        self._thread = None
        self._process = None
        self._run_id = None
        self._cancelled = threading.Event()
        with library._db() as connection:
            unfinished = connection.execute('SELECT id FROM runs').fetchall()
        for row in unfinished:
            report = library.run(row['id'])
            if report['state'] == 'running':
                library.write_report(row['id'], {**report, 'state': 'interrupted', 'errors': ['Aplicativo encerrado antes da conclusão. Execute novamente.']})
        atexit.register(self.shutdown)

    def start(self, folder_id, cycle_id, environment, secrets):
        if not self.runtime.available: raise ValueError(self.runtime.message or 'Playwright indisponível.')
        worker = recorder_root()
        missing = [name for name in ('suite-runtime.cjs', 'suite-reporter.cjs') if not (worker / name).is_file()]
        if missing:
            raise ValueError('Instalação de automação incompleta. Arquivos ausentes: ' + ', '.join(missing) + '.')
        with self._lock:
            if self._thread and self._thread.is_alive(): raise RuntimeError('Já existe uma suíte em execução. Aguarde ou cancele.')
            scripts = self.library.scripts(folder_id, cycle_id)
            if not scripts: raise ValueError('Este ciclo ou pasta ainda não possui scripts.')
            run = self.library.create_run(folder_id, cycle_id, scripts)
            self._run_id = run['id']
            self._cancelled.clear()
            self._thread = threading.Thread(target=self._run, args=(run['id'], scripts, dict(environment), list(secrets)), daemon=True)
            self._thread.start()
            return run

    def _run(self, run_id, scripts, environment, secrets):
        try:
            self._execute(run_id, scripts, environment, secrets)
        except Exception:
            report = self.library.run(run_id)
            self.library.write_report(run_id, {**report, 'state': 'error', 'errors': ['Não foi possível executar a suíte. Verifique Node, Playwright e os scripts.']}, secrets)

    def _execute(self, run_id, scripts, environment, secrets):
        path = self.library.run_path(run_id)
        worker = recorder_root()
        config = {'testDir': str(path / 'scripts'), 'timeout': 30000, 'retries': 0, 'workers': 1,
                  'reporter': [[str(worker / 'suite-reporter.cjs')]], 'outputDir': str(path / 'artifacts'),
                  'use': {'headless': True, 'trace': 'off', 'screenshot': 'off'}}
        (path / 'playwright.config.cjs').write_text('module.exports = ' + json.dumps(config) + ';', encoding='utf-8')
        hook = (worker / 'suite-runtime.cjs').as_posix()
        env = {**os.environ, **environment, 'RECORDER_PLAYWRIGHT_MODULE': self.runtime.playwright_entry,
               'TESTAIZE_SUITE_REPORT': str(path / 'report.json'), 'TESTAIZE_SUITE_SECRETS': json.dumps(secrets),
               'TESTAIZE_SUITE_CONFIG': str(path / 'playwright.config.cjs'),
               'NODE_OPTIONS': (os.environ.get('NODE_OPTIONS', '') + f' --require "{hook}"').strip()}
        process = subprocess.Popen([self.runtime.node, '--eval', _PLAYWRIGHT_LAUNCHER],
                                   cwd=path, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        with self._lock:
            self._process = process
            if self._cancelled.is_set(): self._terminate(process)
        timed_out = False
        try:
            process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate(process)
        finally:
            if process.stdin: process.stdin.close()
            with self._lock: self._process = None
        report = self.library.run(run_id)
        if self._cancelled.is_set(): report.update(state='cancelled', errors=['Execução cancelada.'])
        elif timed_out: report.update(state='error', errors=['A suíte excedeu o limite de cinco minutos.'])
        elif report['state'] == 'running': report.update(state='error', errors=['O runner terminou sem concluir o relatório. Verifique os scripts.'])
        elif process.returncode and not report.get('failed') and not report.get('errors'):
            report.update(state='error', errors=['Falha ao executar os scripts.'])
        self.library.write_report(run_id, report, secrets)

    def status(self, run_id):
        report = self.library.run(run_id)
        with self._lock:
            if run_id == self._run_id and self._thread and self._thread.is_alive() and report['state'] != 'running':
                return {**report, 'state': 'running', 'current': 'Finalizando runner…'}
        return report

    def _terminate(self, process):
        if process.poll() is not None: return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        else: process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)

    def cancel(self, run_id):
        with self._lock:
            if run_id != self._run_id or not self._thread or not self._thread.is_alive(): return self.status(run_id)
            self._cancelled.set()
            if self._process: self._terminate(self._process)
        return self.status(run_id)

    def wait(self):
        if self._thread: self._thread.join(timeout=self.timeout + 15)

    def shutdown(self):
        with self._lock:
            self._cancelled.set()
            if self._process: self._terminate(self._process)
        if self._thread and self._thread is not threading.current_thread(): self._thread.join(timeout=15)
