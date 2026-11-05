"""Bug HTTP surface. Application-wide CSRF/origin checks also cover this blueprint."""
import io
import json
import sqlite3
from functools import wraps

from flask import Blueprint, current_app, jsonify, render_template, request, send_file

from .bugs_coordinator import coordinated, StateConflict, RecoveryPending

blueprint = Blueprint('bugs', __name__)


@blueprint.context_processor
def presentation():
    from .bugs_service import SEVERITIES, severity_key
    return dict(bug_severities=SEVERITIES, severity_key=severity_key,
                bug_status_labels={'aberto': 'Aberto', 'em_reteste': 'Em reteste',
                                   'reaberto': 'Reaberto', 'finalizado': 'Finalizado'})


def service():
    return current_app.extensions['bugs']


def api(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except RecoveryPending as error:
            return jsonify(error=str(error), operation_id=error.operation_id, recovery_pending=True), 503
        except StateConflict as error:
            return jsonify(error=str(error)), 409
        except LookupError as error:
            return jsonify(error=str(error)), 404
        except (ValueError, TypeError) as error:
            return jsonify(error=str(error)), 422
        except (OSError, sqlite3.DatabaseError):
            current_app.logger.exception('Falha na persistência de bug')
            return jsonify(error='Falha ao salvar ou ler o bug. Recarregue para conferir o estado.'), 503
    return wrapped


def body():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError('Envie um objeto JSON válido.')
    return payload


@blueprint.get('/bugs')
def board():
    bugs = service().list()
    columns = [(state, label, [bug for bug in bugs if bug['status'] == state]) for state, label in
               [('aberto', 'Abertos'), ('em_reteste', 'Em reteste'), ('reaberto', 'Reabertos'), ('finalizado', 'Finalizados')]]
    return render_template('bugs_board.html', columns=columns)


@blueprint.get('/sessao/<session_id>/bugs')
@api
def session_bugs(session_id):
    from .storage import find_directory, read_session
    directory = find_directory(service().root, session_id)
    if directory is None:
        raise LookupError('Sessão não encontrada.')
    return render_template('bugs_session.html', record=read_session(directory), bugs=service().list(session_id),
                           available=service().list())


@blueprint.get('/sessao/<session_id>/bugs/novo')
@api
def new(session_id):
    from .storage import find_directory, read_session
    directory = find_directory(service().root, session_id)
    if directory is None:
        raise LookupError('Sessão não encontrada.')
    case_id = request.args.get('precondition_case', type=int)
    if 'precondition_case' in request.args and case_id not in {c['id'] for c in read_session(directory)['cases']}:
        raise ValueError('Pré-condição inválida.')
    return render_template('bug_detail.html', bug=None, session_id=session_id, origin_case_id=case_id)


@blueprint.get('/bugs/<bug_id>')
@api
def detail(bug_id):
    return render_template('bug_detail.html', bug=service().detail(bug_id), session_id=request.args.get('session_id', ''),
                           origin_case_id=None)


@blueprint.post('/api/sessao/<session_id>/bugs')
@api
def create(session_id):
    payload = json.loads(request.form.get('document', '{}'))
    if not isinstance(payload, dict):
        raise ValueError('Documento inválido.')
    if any(len(request.files.getlist(key)) != 1 for key in request.files):
        raise ValueError('Referência de upload duplicada.')
    files = {key: (incoming.read(10 * 1024 * 1024 + 1), incoming.filename or 'imagem')
             for key, incoming in request.files.items()}
    case_id = request.args.get('precondition_case', type=int)
    if 'precondition_case' in request.args and case_id is None:
        raise ValueError('Pré-condição inválida.')
    bug = service().create(payload, files, session_id, 'precondicao' if case_id is not None else 'sessao', case_id)
    return jsonify(bug=bug), 201


@blueprint.get('/api/bugs/<bug_id>')
@api
def get(bug_id):
    return jsonify(bug=service().get(bug_id))


@blueprint.post('/api/bugs/<bug_id>')
@api
def edit(bug_id):
    return jsonify(bug=service().edit(bug_id, body()))


@blueprint.post('/api/bugs/<bug_id>/evidencias')
@api
def evidence(bug_id):
    incoming = request.files.get('imagem')
    item = service().add_evidence(bug_id, request.form.get('kind', 'abertura'),
                                  incoming.read(10 * 1024 * 1024 + 1) if incoming else None,
                                  incoming.filename if incoming else '', request.form.get('note', ''),
                                  request.form.get('token') or None)
    return jsonify(evidence=item), 201


@blueprint.get('/bugs/<bug_id>/evidencias/<evidence_id>')
@api
def image(bug_id, evidence_id):
    content, mime = service().evidence_bytes(bug_id, evidence_id)
    return send_file(io.BytesIO(content), mimetype=mime, max_age=0)


@blueprint.delete('/api/bugs/<bug_id>/evidencias/<evidence_id>')
@api
def remove_evidence(bug_id, evidence_id):
    service().remove_evidence(bug_id, evidence_id)
    return jsonify(ok=True)


@blueprint.get('/api/bugs/<bug_id>/sessao/<session_id>/vinculos')
@api
def preview(bug_id, session_id):
    return jsonify(cases=service().preview(bug_id, session_id))


@blueprint.post('/api/bugs/<bug_id>/sessao/<session_id>/vinculos')
@api
def link(bug_id, session_id):
    from .storage import case_state, find_directory
    with coordinated(service().root):
        result = service().link(bug_id, session_id, body().get('case_ids'))
        directory = find_directory(service().root, session_id)
        result['case_states'] = {item['id']: case_state(directory, item['id']) for item in result['results']}
    return jsonify(ok=True, **result)


@blueprint.delete('/api/bugs/<bug_id>/sessao/<session_id>/vinculos/<int:case_id>')
@api
def unlink(bug_id, session_id, case_id):
    service().unlink(bug_id, session_id, case_id)
    return jsonify(ok=True)


@blueprint.post('/api/bugs/<bug_id>/estado')
@api
def transition(bug_id):
    payload = body()
    return jsonify(bug=service().transition(bug_id, payload.get('target'), payload.get('expected_state'), payload.get('token')))


@blueprint.post('/bugs/<bug_id>/pdf')
@api
def pdf(bug_id):
    from .bugs_export import generate_bug_pdf
    path = generate_bug_pdf(service(), bug_id)
    # Copy before another export can replace the published report.
    return send_file(io.BytesIO(path.read_bytes()), mimetype='application/pdf', as_attachment=True,
                     download_name=f'bug-{bug_id[:8]}.pdf')
