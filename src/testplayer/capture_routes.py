"""Local capture routes. The host authenticates with an ephemeral header, never a URL."""

from __future__ import annotations

import base64
import hmac
import json
from pathlib import Path

from flask import current_app, jsonify, request, session, url_for

from .capture_context import CaptureBroker, PublishedContext
from .capture_service import CaptureError, commit_capture, load_case_context, save_observed_text
from .storage import RevisionConflict, StaleExecution, db as open_db, find_directory


def _same(left: str, right: str) -> bool:
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    left_bytes = left.encode()
    right_bytes = right.encode()
    if len(left_bytes) != len(right_bytes):
        return False
    return hmac.compare_digest(left_bytes, right_bytes)


def _broker() -> CaptureBroker:
    return current_app.extensions["capture_broker"]


def _host_ok() -> bool:
    return _same(request.headers.get("X-Testaize-Capture", ""), _broker().token)


def _web_ok() -> bool:
    return _same(session.get("csrf_token", ""), request.headers.get("X-CSRF-Token", ""))


def _json_error(error: Exception, status: int, code: str):
    payload = {"error": str(error), "code": code}
    if isinstance(error, RevisionConflict):
        document = None
        if error.actual_doc:
            try:
                document = json.loads(error.actual_doc)
            except json.JSONDecodeError:
                document = None
        payload.update(revision=error.revision, actual=error.actual, actual_doc=document)
    return jsonify(payload), status


def _directory(root: Path, session_id: object) -> Path | None:
    if not isinstance(session_id, str):
        return None
    return find_directory(root, session_id)


def _context_payload(root: Path, broker: CaptureBroker) -> dict:
    current = broker.context
    base = {"instance_id": broker.instance_id, "hotkey_ok": broker.hotkey_ok}
    if current is None:
        return {**base, "valid": False, "code": "NO_CONTEXT",
                "message": "Nenhum caso está aberto no Test Player."}
    directory = _directory(root, current.session_id)
    if directory is None:
        return {**base, "valid": False, "code": "INVALID_TARGET",
                "message": "A sessão aberta não está mais disponível."}
    try:
        loaded = load_case_context(directory, current.case_id, current.step_id)
    except CaptureError as exc:
        return {**base, "valid": False, "code": exc.code, "message": str(exc)}
    stale = loaded["execution_generation"] != current.execution_generation or not current.valid
    label = f"Anexar ao passo {loaded['step_position']} — {loaded['step_action']}"
    return {
        **base,
        "valid": not stale,
        "code": "STALE_EXECUTION" if stale else "",
        "message": "O caso recebeu outra execução. Selecione o passo de novo." if stale else "",
        "session_id": current.session_id,
        "case_id": loaded["case_id"],
        "case_name": loaded["case_name"],
        "step_id": loaded["step_id"],
        "execution_generation": loaded["execution_generation"],
        "context_revision": current.context_revision,
        "result_revision": loaded["result_revision"],
        "observed": loaded["observed"],
        "status": loaded["status"],
        "steps": loaded["steps"],
        "attach_label": label[:120],
        "source_client_id": current.source_client_id,
    }


def _publish(root: Path, broker: CaptureBroker, body: dict, source_client_id: str) -> dict:
    session_id = body.get("session_id")
    case_id = body.get("case_id")
    step_id = body.get("step_id")
    event_id = body.get("event_id")
    generation = body.get("execution_generation")
    if not isinstance(session_id, str) or type(case_id) is not int or type(step_id) is not int:
        raise CaptureError("INVALID_TARGET", "Selecione um passo válido.", 422)
    if not isinstance(event_id, str) or not event_id:
        raise CaptureError("INVALID_TARGET", "Evento de seleção inválido.", 422)
    directory = _directory(root, session_id)
    if directory is None:
        raise CaptureError("INVALID_TARGET", "Sessão não encontrada.", 404)
    loaded = load_case_context(directory, case_id, step_id)
    if broker.remember(event_id) and broker.context is not None:
        return _context_payload(root, broker)
    explicit = source_client_id == "capture-host" or generation == loaded["execution_generation"]
    published = PublishedContext(
        session_id=session_id,
        case_id=case_id,
        step_id=step_id,
        execution_generation=loaded["execution_generation"] if explicit else str(generation or ""),
        source_client_id=source_client_id,
        event_id=event_id,
        context_revision=(broker.context.context_revision + 1) if broker.context else 1,
        valid=explicit,
        code="" if explicit else "STALE_EXECUTION",
    )
    broker.publish(published, {
        "type": "selection",
        "session_id": session_id,
        "case_id": case_id,
        "step_id": step_id,
        "execution_generation": published.execution_generation,
        "context_revision": published.context_revision,
        "source_client_id": source_client_id,
        "event_id": event_id,
        "valid": explicit,
    })
    return _context_payload(root, broker)


def _emit(broker: CaptureBroker, payload: dict) -> None:
    with broker._lock:
        broker._event(payload)


def register_capture_routes(app, root: Path) -> None:
    @app.post("/api/captura/host/ping")
    def capture_ping():
        if not _host_ok():
            return jsonify(error="Cliente não autorizado.", code="UNAUTHORIZED_CLIENT"), 403
        body = request.get_json(silent=True)
        hotkey = body.get("hotkey") if isinstance(body, dict) else None
        _broker().mark_host(hotkey if isinstance(hotkey, bool) else None)
        app.logger.info("captura host vinculado")
        return jsonify(ok=True, instance_id=_broker().instance_id)

    @app.post("/api/captura/host/preparar")
    def capture_prepare():
        if not _host_ok():
            return jsonify(error="Cliente não autorizado.", code="UNAUTHORIZED_CLIENT"), 403
        request_id = _broker().request_prepare()
        app.logger.info("captura preparar")
        return jsonify(ok=True, request_id=request_id)

    @app.get("/api/captura/host/preparar")
    def capture_prepare_status():
        if not _host_ok():
            return jsonify(error="Cliente não autorizado.", code="UNAUTHORIZED_CLIENT"), 403
        ready = _broker().prepare_ready(request.args.get("request_id", ""))
        return jsonify(ready=ready, online=_broker().online_clients() > 0)

    @app.get("/api/captura/host/contexto")
    def capture_host_context():
        if not _host_ok():
            return jsonify(error="Cliente não autorizado.", code="UNAUTHORIZED_CLIENT"), 403
        return jsonify(_context_payload(root, _broker()))

    @app.post("/api/captura/host/selecao")
    def capture_host_select():
        if not _host_ok():
            return jsonify(error="Cliente não autorizado.", code="UNAUTHORIZED_CLIENT"), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="Envie um objeto JSON válido.", code="INVALID_TARGET"), 422
        try:
            payload = _publish(root, _broker(), body, "capture-host")
        except CaptureError as exc:
            app.logger.info("captura selecao recusada code=%s", exc.code)
            return jsonify(error=str(exc), code=exc.code), exc.status
        app.logger.info("captura selecao aceita")
        return jsonify(payload)

    @app.post("/api/captura/host/resultado")
    def capture_host_result():
        if not _host_ok():
            return jsonify(error="Cliente não autorizado.", code="UNAUTHORIZED_CLIENT"), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="Envie um objeto JSON válido.", code="INVALID_TARGET"), 422
        directory = _directory(root, body.get("session_id"))
        if directory is None:
            return jsonify(error="Sessão não encontrada.", code="INVALID_TARGET"), 404
        try:
            saved = save_observed_text(
                directory, body.get("step_id"), body.get("text", ""),
                body.get("expected_revision"), body.get("execution_generation", ""),
            )
        except CaptureError as exc:
            app.logger.info("captura resultado recusado code=%s", exc.code)
            return jsonify(error=str(exc), code=exc.code), exc.status
        except RevisionConflict as exc:
            app.logger.info("captura resultado conflito")
            return _json_error(exc, 409, "REVISION_CONFLICT")
        except StaleExecution as exc:
            _broker().invalidate("STALE_EXECUTION")
            app.logger.info("captura resultado geracao antiga")
            return _json_error(exc, 409, "STALE_EXECUTION")
        except (LookupError, ValueError) as exc:
            return jsonify(error=str(exc), code="INVALID_TARGET"), 422
        _emit(_broker(), {
            "type": "result",
            "session_id": body.get("session_id"),
            "case_id": saved["case_id"],
            "step_id": body.get("step_id"),
            "revision": saved["revision"],
            "actual": saved["actual"],
            "status": saved["status"],
            "source_client_id": "capture-host",
        })
        app.logger.info("captura resultado salvo step=%s revision=%s", body.get("step_id"), saved["revision"])
        return jsonify(ok=True, revision=saved["revision"], status=saved["status"], actual=saved["actual"])

    @app.post("/api/captura/host/anexar")
    def capture_attach():
        if not _host_ok():
            return jsonify(error="Cliente não autorizado.", code="UNAUTHORIZED_CLIENT"), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="Envie um objeto JSON válido.", code="INVALID_TARGET"), 422
        encoded = body.get("image_base64")
        if not isinstance(encoded, str) or len(encoded) > 16_000_000:
            return jsonify(error="Imagem inválida.", code="INVALID_IMAGE"), 415
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError:
            return jsonify(error="Imagem inválida.", code="INVALID_IMAGE"), 415
        directory = _directory(root, body.get("session_id"))
        if directory is None:
            return jsonify(error="Sessão não encontrada.", code="INVALID_TARGET"), 404
        command_id = body.get("command_id")
        try:
            saved = commit_capture(
                directory,
                command_id=command_id,
                step_id=body.get("step_id"),
                case_id=body.get("case_id"),
                execution_generation=body.get("execution_generation", ""),
                expected_revision=body.get("expected_revision"),
                render_revision=str(body.get("render_revision", "")),
                content=content,
            )
        except CaptureError as exc:
            app.logger.info("captura anexo recusado command=%s code=%s", command_id, exc.code)
            return jsonify(error=str(exc), code=exc.code), exc.status
        except RevisionConflict as exc:
            app.logger.info("captura anexo conflito command=%s", command_id)
            return _json_error(exc, 409, "REVISION_CONFLICT")
        except StaleExecution as exc:
            _broker().invalidate("STALE_EXECUTION")
            app.logger.info("captura anexo geracao antiga command=%s", command_id)
            return _json_error(exc, 409, "STALE_EXECUTION")
        session_id = body.get("session_id")
        evidence = {
            "type": "evidence",
            "session_id": session_id,
            "case_id": saved["case_id"],
            "step_id": saved["step_id"],
            "evidence_id": saved["evidence_id"],
            "revision": saved["revision"],
            "status": saved["status"],
            "name": saved["name"],
            "url": url_for("view_image", session_id=session_id, evidence_id=saved["evidence_id"]),
            "delete_url": url_for("delete_image", session_id=session_id, evidence_id=saved["evidence_id"]),
            "source_client_id": "capture-host",
            "command_id": command_id,
            "duplicate": saved["duplicate"],
            "step_position": saved["step_position"],
            "step_action": saved["step_action"],
        }
        _emit(_broker(), evidence)
        app.logger.info(
            "captura anexo command=%s evidence=%s duplicate=%s",
            command_id, saved["evidence_id"], saved["duplicate"],
        )
        return jsonify(ok=True, **{key: value for key, value in evidence.items() if key != "type"})

    @app.get("/api/captura/host/operacao/<command_id>")
    def capture_operation(command_id: str):
        if not _host_ok():
            return jsonify(error="Cliente não autorizado.", code="UNAUTHORIZED_CLIENT"), 403
        directory = _directory(root, request.args.get("session_id", ""))
        if directory is None:
            return jsonify(error="Sessão não encontrada.", code="INVALID_TARGET"), 404
        with open_db(directory) as connection:
            row = connection.execute(
                "SELECT evidence_id,step_id FROM capture_commands WHERE command_id=?", (command_id,)
            ).fetchone()
        if row is None:
            return jsonify(ok=False, code="LOCAL_SERVICE_UNAVAILABLE",
                           error="Operação ainda não confirmada."), 404
        return jsonify(ok=True, evidence_id=row["evidence_id"], step_id=row["step_id"], command_id=command_id)

    @app.post("/api/captura/web/contexto")
    def capture_web_context():
        if not _web_ok():
            return jsonify(error="Token de segurança inválido. Recarregue a página."), 400
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="Envie um objeto JSON válido.", code="INVALID_TARGET"), 422
        client_id = body.get("client_id") if isinstance(body.get("client_id"), str) else ""
        _broker().pulse(client_id)
        try:
            payload = _publish(root, _broker(), body, client_id or "player")
        except CaptureError as exc:
            return jsonify(error=str(exc), code=exc.code), exc.status
        return jsonify(payload)

    @app.get("/api/captura/web/eventos")
    def capture_web_events():
        if not _web_ok():
            return jsonify(error="Token de segurança inválido. Recarregue a página."), 400
        client_id = request.args.get("client_id", "")
        _broker().pulse(client_id)
        try:
            after = int(request.args.get("after", "0"))
        except ValueError:
            after = 0
        events, cursor, hotkey = _broker().poll(max(0, after))
        return jsonify(events=events, cursor=cursor, hotkey=hotkey)

    @app.post("/api/captura/web/preparado")
    def capture_web_prepared():
        if not _web_ok():
            return jsonify(error="Token de segurança inválido. Recarregue a página."), 400
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="Envie um objeto JSON válido."), 422
        _broker().ack_prepare(str(body.get("request_id", "")))
        _broker().pulse(str(body.get("client_id", "")))
        return jsonify(ok=True)
