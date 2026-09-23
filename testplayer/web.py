from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import secrets
import shutil
import uuid
from pathlib import Path, PureWindowsPath

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import HTTPException
from PIL import Image, UnidentifiedImageError

from .importer import FIELDS, LABELS, inspect_file
from .attachments import (MAX_ATTACHMENT_BYTES, MAX_STEP_ATTACHMENTS, attachment_content_type,
                          attachment_extension, safe_attachment_name, verified_attachment_bytes)
from .pdf_export import generate_pdf
from .html_export import generate_html
from .bug_prompt import build_prompt, failed_case
from .storage import (create_draft, db, ensure_root, finalize, find_directory, get_meta,
                      list_sessions, migrate_sessions, now, read_session, recover_promotions,
                      remove_session, rerun, save_case, save_result, start_case_run)


MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {"PNG": ("image/png", ".png"), "JPEG": ("image/jpeg", ".jpg"), "WEBP": ("image/webp", ".webp")}
STATUSES = ("aprovado", "reprovado", "bloqueado", "em_andamento", "nao_executado")


def folder_label(path: str) -> str:
    parts = [part.strip() for part in path.replace("\\", "/").split("/") if part.strip()]
    if not parts:
        return "Sem pasta"
    return parts[-2] if len(parts) >= 3 else parts[-1]


def folder_groups(cases: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for case in cases:
        folder = case["folder"] or ""
        if folder not in groups:
            groups[folder] = {"name": folder, "label": folder_label(folder), "cases": [],
                              "counts": {status: 0 for status in STATUSES}}
        group = groups[folder]
        group["cases"].append(case)
        group["counts"][case["status"]] += 1
    for group in groups.values():
        total = len(group["cases"])
        group["total"] = total
        group["done"] = sum(group["counts"][status] for status in STATUSES[:3])
        group["percent"] = round(group["done"] / total * 100) if total else 0
    return list(groups.values())


def create_app(root: Path) -> Flask:
    root = root.resolve()
    ensure_root(root)
    migrate_sessions(root)
    recover_promotions(root)
    secret_path = root / "config" / "chave-local.bin"
    if not secret_path.exists():
        secret_path.write_bytes(secrets.token_bytes(32))
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = secret_path.read_bytes()
    app.config.update(
        TRUSTED_HOSTS=["127.0.0.1", "localhost"],
        MAX_CONTENT_LENGTH=MAX_IMPORT_BYTES,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
    )
    app.config["DATA_ROOT"] = str(root)

    @app.context_processor
    def inject():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return {"csrf_token": token, "status_labels": {
            "nao_executado": "Não executado", "em_andamento": "Em andamento",
            "aprovado": "Aprovado", "reprovado": "Reprovado", "bloqueado": "Bloqueado",
        }}

    @app.before_request
    def check_csrf():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            expected = session.get("csrf_token", "")
            supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            if not expected or not hmac.compare_digest(expected, supplied):
                abort(400, "Token de segurança inválido. Recarregue a página.")
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                abort(403, "Origem não permitida.")

    @app.errorhandler(413)
    def too_large(error):
        if request.path.startswith("/api/"):
            return jsonify(error="Arquivo grande demais para o limite configurado."), 413
        flash("Arquivo grande demais para o limite configurado.", "error")
        return redirect(url_for("home"))

    @app.get("/health")
    def health():
        return jsonify(ok=True)

    @app.get("/")
    def home():
        items = list_sessions(root)
        drafts = [item for item in items if item["state"] == "rascunho"]
        completed = [item for item in items if item["state"] == "concluida"]
        return render_template("home.html", drafts=drafts, completed=completed)

    @app.post("/sessao/<session_id>/excluir")
    def delete_session(session_id: str):
        action = request.form.get("action")
        if action not in ("move", "delete"):
            abort(400, "Escolha o destino da sessão.")
        try:
            remove_session(root, session_id, delete_files=action == "delete")
            flash("Sessão e arquivos excluídos." if action == "delete"
                  else "Sessão movida para a pasta Excluídas.", "success")
        except LookupError:
            abort(404)
        except (ValueError, OSError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("home"))

    @app.post("/importar")
    def upload():
        incoming = request.files.get("arquivo")
        if incoming is None or not incoming.filename:
            flash("Selecione um arquivo .xlsx ou CSV UTF-8.", "error")
            return redirect(url_for("home"))
        filename = PureWindowsPath(incoming.filename).name[:180]
        suffix = Path(filename).suffix.lower()
        if suffix not in (".xlsx", ".csv"):
            flash("Formato aceito: .xlsx ou .csv UTF-8.", "error")
            return redirect(url_for("home"))
        token = uuid.uuid4().hex
        temporary = root / "temporarios" / token
        temporary.mkdir()
        target = temporary / f"entrada{suffix}"
        try:
            incoming.save(target)
            if target.stat().st_size > MAX_IMPORT_BYTES:
                raise ValueError("Arquivo maior que 25 MB.")
            (temporary / "info.json").write_text(json.dumps({"original_name": filename}, ensure_ascii=False), encoding="utf-8")
            return redirect(url_for("preview", token=token))
        except Exception as exc:
            shutil.rmtree(temporary, ignore_errors=True)
            flash(str(exc), "error")
            return redirect(url_for("home"))

    def temp_source(token: str):
        try:
            uuid.UUID(hex=token)
        except ValueError:
            abort(404)
        directory = root / "temporarios" / token
        info_path = directory / "info.json"
        if not info_path.is_file():
            abort(404)
        sources = list(directory.glob("entrada.*"))
        if len(sources) != 1:
            abort(404)
        return directory, sources[0], json.loads(info_path.read_text(encoding="utf-8"))

    @app.route("/previa/<token>", methods=["GET", "POST"])
    def preview(token: str):
        temporary, source, info = temp_source(token)
        manual = None
        if request.method == "POST":
            manual = {}
            for field in FIELDS:
                raw = request.form.get(f"map_{field}", "")
                if raw != "":
                    try:
                        manual[field] = int(raw)
                    except ValueError:
                        flash("Mapeamento de coluna inválido.", "error")
                        return redirect(url_for("preview", token=token))
            if not manual:
                manual = None
        try:
            parsed = inspect_file(source, manual)
        except ValueError as exc:
            parsed = {"filename": info["original_name"], "sheets": [], "errors": [str(exc)],
                      "total_cases": 0, "total_steps": 0, "headers": [], "mapping": {}}
        parsed["filename"] = info["original_name"]
        all_names = [sheet["name"] for sheet in parsed["sheets"]]
        selected = set(request.form.getlist("sheet")) if request.method == "POST" else set(all_names)
        selected &= set(all_names)
        selected_cases = sum(len(sheet["cases"]) for sheet in parsed["sheets"] if sheet["name"] in selected)
        selected_steps = sum(sheet["steps"] for sheet in parsed["sheets"] if sheet["name"] in selected)
        selected_errors = parsed["errors"] + [f"{sheet['name']}: {error}" for sheet in parsed["sheets"]
                                               if sheet["name"] in selected for error in sheet["errors"]]
        if request.method == "POST" and request.form.get("action") == "start":
            if selected_errors or not selected or not selected_cases:
                flash("Revise o mapeamento, selecione abas válidas e corrija os erros antes de iniciar.", "error")
            else:
                session_id = create_draft(root, parsed, source, selected, info["original_name"])
                shutil.rmtree(temporary, ignore_errors=True)
                return redirect(url_for("player", session_id=session_id))
        return render_template("preview.html", token=token, parsed=parsed, labels=LABELS, fields=FIELDS,
                               selected=selected, selected_cases=selected_cases, selected_steps=selected_steps,
                               selected_errors=selected_errors)

    def session_dir(session_id: str) -> Path:
        directory = find_directory(root, session_id)
        if directory is None:
            abort(404)
        return directory

    @app.get("/sessao/<session_id>")
    def player(session_id: str):
        directory = session_dir(session_id)
        record = read_session(directory)
        groups = folder_groups(record["cases"])
        initial_folders = request.args.getlist("pasta")
        if not set(initial_folders).issubset({group["name"] for group in groups}):
            abort(404)
        return render_template("player.html", record=record, writable=True,
                               folder_groups=groups, initial_folders=initial_folders)

    @app.get("/sessao/<session_id>/abrir")
    def choose_folder(session_id: str):
        record = read_session(session_dir(session_id))
        return render_template("choose_folder.html", record=record,
                               folder_groups=folder_groups(record["cases"]),
                               all_progress={"total": len(record["cases"]), "counts": record["counts"],
                                             "done": sum(record["counts"][status] for status in STATUSES[:3])})

    @app.get("/sessao/<session_id>/kanban")
    def kanban(session_id: str):
        record = read_session(session_dir(session_id))
        groups = folder_groups(record["cases"])
        chosen = request.args.getlist("pasta")
        valid = {group["name"] for group in groups}
        if not set(chosen).issubset(valid):
            abort(404)
        shown = [case for case in record["cases"] if not chosen or case["folder"] in chosen]
        return render_template("kanban.html", record=record, folder_groups=groups, chosen=chosen,
                               columns=[(status, label, [case for case in shown if case["status"] == status])
                                        for status, label in (("nao_executado", "Não executado"),
                                                              ("em_andamento", "Em andamento"),
                                                              ("aprovado", "Aprovado"),
                                                              ("reprovado", "Reprovado"),
                                                              ("bloqueado", "Bloqueado"))])

    @app.post("/api/sessao/<session_id>/passo/<int:step_id>")
    def result(session_id: str, step_id: int):
        directory = session_dir(session_id)
        body = request.get_json(silent=True) or {}
        try:
            comment = body.get("comment")
            changed_at = save_result(directory, step_id, body.get("status", ""), str(body.get("actual", "")),
                                     str(comment) if comment is not None else None,
                                     status_action=body.get("status_action") is True,
                                     actual_doc=body.get("actual_doc"))
            record = read_session(directory)
            return jsonify(ok=True, counts=record["counts"], status_changed_at=changed_at)
        except LookupError as exc:
            return jsonify(error=str(exc)), 404
        except ValueError as exc:
            return jsonify(error=str(exc)), 422

    @app.post("/api/sessao/<session_id>/caso/<int:case_id>")
    def case_result(session_id: str, case_id: int):
        directory = session_dir(session_id)
        body = request.get_json(silent=True) or {}
        try:
            save_case(directory, case_id, str(body.get("status", "")), str(body.get("comment", "")),
                      comment_doc=body.get("comment_doc"), precondition_doc=body.get("precondition_doc"))
            record = read_session(directory)
            case = next(item for item in record["cases"] if item["id"] == case_id)
            return jsonify(ok=True, status=case["status"], counts=record["counts"])
        except StopIteration:
            return jsonify(error="Caso não encontrado."), 404
        except LookupError as exc:
            return jsonify(error=str(exc)), 404
        except ValueError as exc:
            return jsonify(error=str(exc)), 422

    @app.post("/api/sessao/<session_id>/passo/<int:step_id>/imagem")
    def upload_image(session_id: str, step_id: int):
        directory = session_dir(session_id)
        incoming = request.files.get("imagem")
        if incoming is None:
            return jsonify(error="Escolha uma imagem."), 400
        content = incoming.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES:
            return jsonify(error="Imagem maior que 10 MB."), 413
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                kind = image.format
                width, height = image.size
            if kind not in IMAGE_TYPES or width * height > 40_000_000:
                raise ValueError("Use PNG, JPEG ou WebP com até 40 megapixels.")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            return jsonify(error=str(exc) or "Imagem inválida."), 415
        mime, extension = IMAGE_TYPES[kind]
        with db(directory) as connection:
            meta = get_meta(connection)
            step = connection.execute("SELECT s.position,s.case_id FROM steps s WHERE s.id=?", (step_id,)).fetchone()
            count = connection.execute("SELECT COUNT(*) FROM evidence WHERE step_id=?", (step_id,)).fetchone()[0]
            if step is None:
                return jsonify(error="Passo não encontrado."), 404
            if count >= 12:
                return jsonify(error="Limite de 12 imagens por passo."), 413
            image_id = uuid.uuid4().hex
            relative = Path("evidencias") / f"caso-{step['case_id']}" / f"passo-{step['position']}" / f"{image_id}{extension}"
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix(target.suffix + ".tmp")
            try:
                temp.write_bytes(content)
                os.replace(temp, target)
                with connection:
                    connection.execute(
                        "INSERT INTO evidence(id,step_id,relative_path,original_name,mime,size,sha256,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (image_id, step_id, relative.as_posix(), PureWindowsPath(incoming.filename or "Imagem colada").name[:180],
                         mime, len(content), hashlib.sha256(content).hexdigest(), now()),
                    )
            except Exception:
                temp.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                raise
        return jsonify(ok=True, id=image_id,
                       url=url_for("view_image", session_id=session_id, evidence_id=image_id),
                       delete_url=url_for("delete_image", session_id=session_id, evidence_id=image_id)), 201

    @app.post("/api/sessao/<session_id>/passo/<int:step_id>/arquivo")
    def upload_step_attachment(session_id: str, step_id: int):
        directory = session_dir(session_id)
        if request.content_length and request.content_length > MAX_ATTACHMENT_BYTES + 1_000_000:
            return jsonify(error="Cada arquivo pode ter no máximo 5 MB."), 413
        incoming = request.files.get("arquivo")
        if incoming is None or not incoming.filename:
            return jsonify(error="Escolha um arquivo."), 400
        try:
            original_name = safe_attachment_name(incoming.filename)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        content = incoming.read(MAX_ATTACHMENT_BYTES + 1)
        if len(content) > MAX_ATTACHMENT_BYTES:
            return jsonify(error="Cada arquivo pode ter no máximo 5 MB."), 413
        if not content:
            return jsonify(error="Arquivo vazio."), 400
        extension = attachment_extension(original_name)
        content_type = attachment_content_type(original_name, incoming.mimetype)
        with db(directory) as connection:
            connection.execute("BEGIN IMMEDIATE")
            step = connection.execute("SELECT s.position,s.case_id FROM steps s WHERE s.id=?", (step_id,)).fetchone()
            if step is None:
                return jsonify(error="Passo não encontrado."), 404
            count = connection.execute("SELECT COUNT(*) FROM step_attachments WHERE step_id=?", (step_id,)).fetchone()[0]
            if count >= MAX_STEP_ATTACHMENTS:
                return jsonify(error=f"Limite de {MAX_STEP_ATTACHMENTS} arquivos por passo."), 413
            file_id = uuid.uuid4().hex
            relative = Path("anexos") / f"caso-{step['case_id']}" / f"passo-{step['position']}" / file_id
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".tmp")
            try:
                temporary.write_bytes(content)
                os.replace(temporary, target)
                with connection:
                    connection.execute(
                        "INSERT INTO step_attachments(id,step_id,relative_path,original_name,extension,content_type,size,sha256,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (file_id, step_id, relative.as_posix(), original_name, extension, content_type, len(content),
                         hashlib.sha256(content).hexdigest(), now()),
                    )
            except Exception:
                temporary.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                raise
        return jsonify(ok=True, id=file_id, name=original_name, extension=extension,
                       content_type=content_type, size=len(content),
                       url=url_for("download_step_attachment", session_id=session_id, file_id=file_id),
                       delete_url=url_for("delete_step_attachment", session_id=session_id, file_id=file_id)), 201

    @app.get("/sessao/<session_id>/arquivo/<file_id>")
    def download_step_attachment(session_id: str, file_id: str):
        directory = session_dir(session_id)
        with db(directory) as connection:
            item = connection.execute("SELECT relative_path,original_name,size,sha256 FROM step_attachments WHERE id=?", (file_id,)).fetchone()
            if item is None:
                item = connection.execute("SELECT relative_path,original_name,size,sha256 FROM archived_attachments WHERE id=?", (file_id,)).fetchone()
        if item is None:
            abort(404)
        try:
            name = safe_attachment_name(item["original_name"])
            content = verified_attachment_bytes(directory, dict(item))
        except ValueError:
            abort(409, "Arquivo anexado indisponível ou com integridade divergente.")
        response = send_file(io.BytesIO(content), mimetype="application/octet-stream", as_attachment=True,
                             download_name=name)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Download-Options"] = "noopen"
        return response

    @app.post("/api/sessao/<session_id>/arquivo/<file_id>/excluir")
    def delete_step_attachment(session_id: str, file_id: str):
        directory = session_dir(session_id)
        with db(directory) as connection:
            item = connection.execute("SELECT relative_path FROM step_attachments WHERE id=?", (file_id,)).fetchone()
            if item is None:
                return jsonify(error="Arquivo não encontrado nesta execução."), 404
            with connection:
                connection.execute("DELETE FROM step_attachments WHERE id=?", (file_id,))
        path = (directory / item["relative_path"]).resolve()
        if path.is_relative_to(directory.resolve()):
            path.unlink(missing_ok=True)
        return jsonify(ok=True)

    @app.post("/api/sessao/<session_id>/caso/<int:case_id>/evidencia/<scope>")
    def upload_case_image(session_id: str, case_id: int, scope: str):
        if scope not in {"precondition", "comment"}:
            abort(404)
        directory = session_dir(session_id)
        incoming = request.files.get("imagem")
        if incoming is None:
            return jsonify(error="Escolha uma imagem."), 400
        content = incoming.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES:
            return jsonify(error="Imagem maior que 10 MB."), 413
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                kind = image.format
                width, height = image.size
            if kind not in IMAGE_TYPES or width * height > 40_000_000:
                raise ValueError("Use PNG, JPEG ou WebP com até 40 megapixels.")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            return jsonify(error=str(exc) or "Imagem inválida."), 415
        mime, extension = IMAGE_TYPES[kind]
        with db(directory) as connection:
            if connection.execute("SELECT 1 FROM cases WHERE id=?", (case_id,)).fetchone() is None:
                return jsonify(error="Caso não encontrado."), 404
            count = connection.execute("SELECT COUNT(*) FROM case_evidence WHERE case_id=? AND scope=?",
                                       (case_id, scope)).fetchone()[0]
            if count >= 12:
                return jsonify(error="Limite de 12 imagens nesta seção."), 413
            image_id = uuid.uuid4().hex
            relative = Path("evidencias") / f"caso-{case_id}" / scope / f"{image_id}{extension}"
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            try:
                temporary.write_bytes(content)
                os.replace(temporary, target)
                with connection:
                    connection.execute(
                        "INSERT INTO case_evidence(id,case_id,scope,relative_path,original_name,mime,size,sha256,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (image_id, case_id, scope, relative.as_posix(),
                         PureWindowsPath(incoming.filename or "Imagem colada").name[:180], mime,
                         len(content), hashlib.sha256(content).hexdigest(), now()),
                    )
            except Exception:
                temporary.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                raise
        return jsonify(ok=True, id=image_id,
                       url=url_for("view_image", session_id=session_id, evidence_id=image_id),
                       delete_url=url_for("delete_image", session_id=session_id, evidence_id=image_id)), 201

    @app.get("/sessao/<session_id>/imagem/<evidence_id>")
    def view_image(session_id: str, evidence_id: str):
        directory = session_dir(session_id)
        with db(directory) as connection:
            item = connection.execute("SELECT relative_path,mime FROM evidence WHERE id=?", (evidence_id,)).fetchone()
            if item is None:
                item = connection.execute("SELECT relative_path,mime FROM case_evidence WHERE id=?", (evidence_id,)).fetchone()
            if item is None:
                item = connection.execute("SELECT relative_path,mime FROM archived_evidence WHERE id=?", (evidence_id,)).fetchone()
        if item is None:
            abort(404)
        path = (directory / item["relative_path"]).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            abort(404)
        response = send_file(path, mimetype=item["mime"], as_attachment=False)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.post("/api/sessao/<session_id>/imagem/<evidence_id>/excluir")
    def delete_image(session_id: str, evidence_id: str):
        directory = session_dir(session_id)
        with db(directory) as connection:
            item = connection.execute("SELECT relative_path FROM evidence WHERE id=?", (evidence_id,)).fetchone()
            if item is None:
                item = connection.execute("SELECT relative_path FROM case_evidence WHERE id=?", (evidence_id,)).fetchone()
                if item is None:
                    return jsonify(error="Imagem não encontrada."), 404
                table = "case_evidence"
            else:
                table = "evidence"
            with connection:
                connection.execute(f"DELETE FROM {table} WHERE id=?", (evidence_id,))
        path = (directory / item["relative_path"]).resolve()
        if path.is_relative_to(directory.resolve()):
            path.unlink(missing_ok=True)
        return jsonify(ok=True)

    @app.post("/sessao/<session_id>/finalizar")
    def finish(session_id: str):
        directory = session_dir(session_id)
        try:
            finalize(root, directory)
            flash("Execução finalizada e salva na pasta de sessões.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("player", session_id=session_id))

    @app.post("/sessao/<session_id>/caso/<int:case_id>/nova-execucao")
    def new_case_run(session_id: str, case_id: int):
        try:
            run_no = start_case_run(session_dir(session_id), case_id)
            flash(f"Execução {run_no} guardada no histórico. Novo reteste iniciado neste caso.", "success")
        except (ValueError, LookupError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("player", session_id=session_id) + f"#caso-{case_id}")

    @app.post("/sessao/<session_id>/nova-execucao")
    def new_execution(session_id: str):
        directory = session_dir(session_id)
        try:
            new_id = rerun(root, directory)
            return redirect(url_for("player", session_id=new_id))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("player", session_id=session_id))

    @app.post("/sessao/<session_id>/gerar-pdf")
    def make_pdf(session_id: str):
        directory = session_dir(session_id)
        try:
            selected, include_history = report_options(directory)
            report = generate_pdf(directory, selected, include_history=include_history)
            return send_file(report, mimetype="application/pdf", as_attachment=True,
                             download_name=f"execucao-{session_id[:8]}.pdf")
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            app.logger.exception("Falha ao gerar PDF da sessão %s", session_id)
            flash(f"Não foi possível gerar o PDF: {type(exc).__name__}.", "error")
            return redirect(url_for("player", session_id=session_id))

    def report_options(directory: Path) -> tuple[set[int], bool]:
        selected = request.form.getlist("case_id")
        if not selected or len(selected) != len(set(selected)) or not all(value.isdecimal() for value in selected):
            abort(400, "Selecione ao menos um caso válido.")
        valid = {str(case["id"]) for case in read_session(directory)["cases"]}
        if not set(selected).issubset(valid):
            abort(400, "Há casos inválidos na seleção.")
        scope = request.form.get("run_scope", "latest")
        if scope not in ("latest", "all"):
            abort(400, "Seleção de execuções inválida.")
        return {int(value) for value in selected}, scope == "all"

    @app.post("/sessao/<session_id>/gerar-html")
    def make_html(session_id: str):
        directory = session_dir(session_id)
        try:
            selected, include_history = report_options(directory)
            report = generate_html(directory, selected, include_history=include_history)
            return send_file(report, mimetype="text/html", as_attachment=True,
                             download_name=f"execucao-{session_id[:8]}.html")
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            app.logger.exception("Falha ao gerar HTML da sessão %s", session_id)
            flash(f"Não foi possível gerar o HTML: {type(exc).__name__}.", "error")
            return redirect(url_for("player", session_id=session_id))

    @app.post("/sessao/<session_id>/caso/<int:case_id>/relatorio-falha")
    def failure_report(session_id: str, case_id: int):
        directory = session_dir(session_id)
        case = next((item for item in read_session(directory)["cases"] if item["id"] == case_id), None)
        if case is None:
            abort(404)
        if not failed_case(case):
            abort(409, "Marque o caso e ao menos um passo como reprovados.")
        run_no = len(case["previous_runs"]) + 1
        try:
            report = generate_pdf(directory, {case_id}, output_name=f"falha-caso-{case_id}-execucao-{run_no}.pdf",
                                  report_kind="failure")
            return send_file(report, mimetype="application/pdf", as_attachment=True,
                             download_name=report.name)
        except Exception:
            app.logger.exception("Falha ao gerar relatório do caso %s", case_id)
            flash("Não foi possível gerar o relatório da falha.", "error")
            return redirect(url_for("player", session_id=session_id) + f"#caso-{case_id}")

    @app.get("/api/sessao/<session_id>/caso/<int:case_id>/prompt-bug")
    def bug_report_prompt(session_id: str, case_id: int):
        case = next((item for item in read_session(session_dir(session_id))["cases"] if item["id"] == case_id), None)
        if case is None:
            abort(404)
        if not failed_case(case):
            abort(409)
        return jsonify(prompt=build_prompt(root, case))

    return app
