"""Library pages and HTTP contracts; recording lifecycle remains in the host."""
from __future__ import annotations
import io

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file

blueprint = Blueprint('automation_library', __name__)


def library(): return current_app.extensions['automation_library']


def payload():
    value = request.get_json(silent=True)
    if not isinstance(value, dict): abort(400, 'Solicitação inválida.')
    return value


def require_runtime():
    runtime = current_app.extensions['automation_runtime']
    if not runtime.available: abort(503, runtime.message)


def library_page(folder_id=None):
    selected = library().folder(folder_id) if folder_id else None
    cycle_id = request.args.get('ciclo') or None
    return render_template('automation_library.html', folders=library().folders(), folder=selected,
                           cycles=library().cycles(folder_id) if selected else [], selected_cycle=cycle_id,
                           scripts=library().scripts(folder_id, cycle_id) if selected else [],
                           runs=library().runs(folder_id, cycle_id) if selected else [])


@blueprint.errorhandler(LookupError)
def missing_item(error):
    if request.path.startswith('/api/'): return jsonify(ok=False, error=str(error)), 404
    return render_template('automation_unavailable.html', reason=str(error)), 404


@blueprint.errorhandler(ValueError)
def invalid_item(error):
    return jsonify(ok=False, error=str(error)), 400


@blueprint.get('/iniciativas/automacao/pastas/<folder_id>')
def folder_page(folder_id):
    require_runtime()
    return library_page(folder_id)


@blueprint.get('/iniciativas/automacao/gravacao')
def recording():
    require_runtime()
    return render_template('automation.html')


@blueprint.get('/iniciativas/automacao/scripts/<script_id>')
def script_page(script_id):
    require_runtime()
    script = library().script(script_id)
    return render_template('automation_script.html', script=script, cycles=library().cycles(script['folder_id']))


@blueprint.get('/api/iniciativas/automacao/biblioteca')
def catalog():
    folders = library().folders()
    return jsonify(folders=[{**folder, 'cycles': library().cycles(folder['id'])} for folder in folders])


@blueprint.post('/api/iniciativas/automacao/pastas')
def create_folder():
    return jsonify(ok=True, item=library().create_folder(payload().get('name'))), 201


@blueprint.post('/api/iniciativas/automacao/ciclos')
def create_cycle():
    value = payload()
    return jsonify(ok=True, item=library().create_cycle(value.get('folder_id'), value.get('name'))), 201


@blueprint.route('/api/iniciativas/automacao/<kind>/<item_id>', methods=['PUT', 'DELETE'])
def mutate_item(kind, item_id):
    table = {'pastas': 'folders', 'ciclos': 'cycles', 'scripts': 'scripts'}.get(kind)
    if not table: abort(404)
    if request.method == 'DELETE':
        library().delete(table, item_id)
        return jsonify(ok=True)
    value = payload()
    if table == 'scripts':
        result = library().save_script(value.get('cycle_id'), value.get('name'), value.get('code'), item_id)
    else: result = library().rename(table, item_id, value.get('name'))
    return jsonify(ok=True, item=result)


@blueprint.post('/api/iniciativas/automacao/scripts')
def save_script():
    value = payload()
    result = library().save_script(value.get('cycle_id'), value.get('name'), value.get('code'), value.get('script_id'))
    return jsonify(ok=True, item=result), 201


@blueprint.get('/api/iniciativas/automacao/scripts/<script_id>/download')
def download_script(script_id):
    script = library().script(script_id)
    filename = script['name'] if script['name'].endswith('.spec.ts') else script['name'] + '.spec.ts'
    return send_file(io.BytesIO(script['code'].encode('utf-8')), mimetype='text/plain; charset=utf-8', as_attachment=True, download_name=filename)


@blueprint.post('/api/iniciativas/automacao/execucoes')
def run_suite():
    require_runtime()
    value = payload()
    vault = current_app.extensions['automation_vault']
    environment = vault.environment()
    secrets = [environment[item['key']] for item in vault.entries() if item['secret'] and item['has_value']]
    try:
        run = current_app.extensions['automation_suite'].start(value.get('folder_id'), value.get('cycle_id') or None, environment, secrets)
    except RuntimeError as error:
        return jsonify(ok=False, error=str(error)), 409
    return jsonify(ok=True, run=run), 202


@blueprint.get('/api/iniciativas/automacao/execucoes/<run_id>')
def suite_status(run_id):
    return jsonify(ok=True, run=current_app.extensions['automation_suite'].status(run_id))


@blueprint.post('/api/iniciativas/automacao/execucoes/<run_id>/cancelar')
def cancel_suite(run_id):
    return jsonify(ok=True, run=current_app.extensions['automation_suite'].cancel(run_id))
