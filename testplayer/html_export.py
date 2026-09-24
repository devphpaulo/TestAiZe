from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .attachments import attachment_extension, verified_attachment_bytes
from .storage import read_session


def _format_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, TypeError):
        return value or "—"


def render_report_html(directory: Path, selected_case_ids: set[int], include_history: bool = False,
                       report_kind: str = "execution", print_all: bool = False,
                       pdf_mode: bool = False) -> str:
    session = read_session(directory)
    chosen = [case for case in session["cases"] if case["id"] in selected_case_ids]
    if not chosen:
        raise ValueError("Selecione ao menos um caso para o relatório.")
    root = directory.resolve()
    images: dict[str, str] = {}

    def blocks(source: list[dict]) -> list[dict]:
        result = []
        for block in source:
            if block["type"] == "text":
                result.append({"type": "text", "text": block["text"]})
            elif block["type"] == "image":
                item = block["item"]
                if item["id"] not in images:
                    path = (directory / item["relative_path"]).resolve()
                    if not path.is_relative_to(root) or not path.is_file():
                        images[item["id"]] = ""
                    else:
                        mime = item["mime"]
                        if mime not in ("image/png", "image/jpeg", "image/webp"):
                            raise ValueError("Formato de evidência inválido.")
                        images[item["id"]] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
                result.append({"type": "image", "src": images[item["id"]],
                               "name": item["original_name"], "width": block["width"]})
        return result

    def run(source: dict, label: str) -> dict:
        def attachment(item: dict) -> dict:
            if pdf_mode:
                return {"name": item["original_name"],
                        "extension": item.get("extension") or attachment_extension(item["original_name"]),
                        "size": item["size"]}
            content = verified_attachment_bytes(directory, item)
            return {"id": item["id"], "name": item["original_name"],
                    "extension": item.get("extension") or attachment_extension(item["original_name"]),
                    "size": len(content), "data": base64.b64encode(content).decode("ascii")}

        return {
            "label": label, "status": source["status"], "precondition": source["precondition"],
            "notes": blocks(source.get("precondition_notes_blocks", source["precondition_blocks"])),
            "comment": blocks(source["comment_blocks"]),
            "steps": [{"position": step["position"], "action": step["action"],
                       "test_data": step["test_data"], "expected": step["expected"],
                       "status": step["status"], "status_changed_at": step["status_changed_at"],
                       "actual": blocks(step["actual_blocks"]),
                       "attachments": [attachment(item)
                                       for item in step.get("attachments", [])]} for step in source["steps"]],
        }

    cases = []
    for case in chosen:
        runs = []
        if include_history:
            for previous in sorted(case["previous_runs"], key=lambda item: item["run_no"]):
                runs.append(run(previous["snapshot"], f"Execução {previous['run_no']} · {previous['captured_at'][:19].replace('T', ' ')}"))
        runs.append(run(case, f"Execução atual · {len(case['previous_runs']) + 1}"))
        cases.append({"id": case["id"], "position": case["position"], "name": case["name"],
                      "folder": case["folder"], "priority": case["priority"],
                      "source_status": case["source_status"], "status": case["status"], "runs": runs})
    payload = json.dumps(cases, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    templates = Path(__file__).resolve().parent / "templates"
    static = Path(__file__).resolve().parent / "static"
    environment = Environment(loader=FileSystemLoader(templates), autoescape=select_autoescape(["html"]))
    logo_src = "data:image/png;base64," + base64.b64encode((static / "report-logo.png").read_bytes()).decode("ascii")
    return environment.get_template("report_export.html").render(
        meta=session["meta"], payload=payload, case_count=len(cases),
        run_count=sum(len(case["runs"]) for case in cases), report_kind=report_kind,
        started_at=_format_time(session["meta"].get("created_at", "")),
        generated_at=_format_time(datetime.now().astimezone().isoformat()),
        report_css=(static / "report.css").read_text(encoding="utf-8"),
        logo_src=logo_src, print_all=print_all, pdf_mode=pdf_mode,
    )


def generate_html(directory: Path, selected_case_ids: set[int], include_history: bool = False) -> Path:
    html = render_report_html(directory, selected_case_ids, include_history)
    target = directory / "relatorios" / "relatorio.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".html.tmp")
    try:
        temporary.write_text(html, encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
