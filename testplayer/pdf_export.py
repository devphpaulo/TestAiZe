from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PILImage
import pymupdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .attachments import attachment_extension, verified_attachment_bytes
from .storage import now, read_session


LABELS = {"nao_executado": "Não executado", "em_andamento": "Em andamento", "aprovado": "Aprovado",
          "reprovado": "Reprovado", "bloqueado": "Bloqueado"}
STATUS_COLORS = {"nao_executado": "#8B95A3", "em_andamento": "#BC8A23", "aprovado": "#27834B",
                 "reprovado": "#C3484D", "bloqueado": "#3579C5"}
INK = colors.HexColor("#172235")
MUTED = colors.HexColor("#607087")
LINE = colors.HexColor("#E3EAF2")
PANEL = colors.HexColor("#F5F9FC")
TEAL = colors.HexColor("#0A9499")


class AttachmentParagraph(Paragraph):
    def __init__(self, text: str, style: ParagraphStyle, marker: str, positions: dict):
        super().__init__(text, style)
        self.marker = marker
        self.positions = positions

    def drawOn(self, canvas, x, y, _sW=0):
        self.positions[self.marker] = (canvas.getPageNumber() - 1, x, y, self.width, self.height)
        return super().drawOn(canvas, x, y, _sW)


def _font() -> str:
    for path in (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/arial.ttf"),
                 Path("C:/Windows/Fonts/DejaVuSans.ttf")):
        if path.is_file():
            if "AppFont" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("AppFont", str(path)))
            return "AppFont"
    return "Helvetica"


def _text(value: object, style: ParagraphStyle, fallback: str = "—") -> Paragraph:
    return Paragraph(escape(str(value or fallback)).replace("\n", "<br/>"), style)


def _time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return value


def _evidence(directory: Path, items: list[dict], styles: dict, width_percent: int = 100) -> list:
    flow = []
    resolved_root = directory.resolve()
    for item in items:
        path = (directory / item["relative_path"]).resolve()
        if not path.is_relative_to(resolved_root) or not path.is_file():
            flow.append(_text(f"Imagem indisponível: {item['original_name']}", styles["small"]))
            continue
        try:
            with PILImage.open(path) as source:
                width, height = source.size
            scale = min((182 * mm * width_percent / 100) / width, (180 * mm) / height, 1)
            picture = Image(str(path), width=width * scale, height=height * scale)
            picture.hAlign = "LEFT"
            flow.extend([Spacer(1, 2 * mm), picture,
                         _text(item["original_name"], styles["caption"]), Spacer(1, 3 * mm)])
        except (OSError, ValueError):
            flow.append(_text(f"Imagem indisponível: {item['original_name']}", styles["small"]))
    return flow


def _section(title: str, content: str, evidence: list[dict], directory: Path, styles: dict) -> list:
    if not content and not evidence:
        return []
    flow = [_text(title.upper(), styles["eyebrow"])]
    if content:
        flow.append(_text(content, styles["body"]))
    if evidence:
        flow.append(_text(f"Evidências anexadas · {len(evidence)}", styles["small"]))
        flow.extend(_evidence(directory, evidence, styles))
    flow.append(Spacer(1, 2 * mm))
    return flow


def _rich_section(title: str, blocks: list[dict], directory: Path, styles: dict) -> list:
    if not any(block["type"] == "image" or block.get("text", "").strip() for block in blocks):
        return []
    flow = [_text(title.upper(), styles["eyebrow"])]
    for block in blocks:
        if block["type"] == "text" and block["text"].strip():
            flow.append(_text(block["text"], styles["body"]))
        elif block["type"] == "image":
            flow.extend(_evidence(directory, [block["item"]], styles, block["width"]))
    flow.append(Spacer(1, 2 * mm))
    return flow


def _embed_step_files(source: Path, target: Path, directory: Path, records: list[dict], positions: dict) -> None:
    with pymupdf.open(source) as pdf:
        for record in records:
            item = record["item"]
            content = verified_attachment_bytes(directory, item)
            marker = record["marker"]
            if marker not in positions:
                raise ValueError(f"O passo do anexo não foi localizado no PDF: {item['original_name']}")
            page_no, x, y, width, height = positions[marker]
            page = pdf[page_no]
            name = item["original_name"]
            description = (f"Caso {record['case_position']} | Execucao {record['run_no']} | "
                           f"Passo {record['step_position']} | {name}")
            embedded_name = f"{marker}{attachment_extension(name)}"
            pdf.embfile_add(embedded_name, content, filename=name, ufilename=name, desc=description)
            # The page annotation gives the reader a visible extraction point beside this step.
            point = pymupdf.Point(min(x + width - 15, page.rect.width - 30), page.rect.height - y - height / 2)
            annotation = page.add_file_annot(point, content, name, ufilename=name,
                                             desc=description, icon="Paperclip")
            annotation.set_colors(stroke=(0.04, 0.58, 0.60))
            annotation.update()
        pdf.save(target, garbage=4, deflate=True)
    with pymupdf.open(target) as check:
        for record in records:
            item = record["item"]
            embedded_name = f"{record['marker']}{attachment_extension(item['original_name'])}"
            if check.embfile_get(embedded_name) != verified_attachment_bytes(directory, item):
                raise ValueError(f"O anexo incorporado ao PDF falhou na verificação: {item['original_name']}")


def generate_pdf(directory: Path, selected_case_ids: set[int] | None = None,
                 include_history: bool = False, output_name: str = "relatorio.pdf",
                 report_kind: str = "execution") -> Path:
    session = read_session(directory)
    chosen = [case for case in session["cases"] if selected_case_ids is None or case["id"] in selected_case_ids]
    if not chosen:
        raise ValueError("Selecione ao menos um caso para o PDF.")
    if Path(output_name).name != output_name or not output_name.endswith(".pdf"):
        raise ValueError("Nome do relatório inválido.")
    report_cases = []
    for case in chosen:
        if include_history:
            for run in sorted(case["previous_runs"], key=lambda item: item["run_no"]):
                previous = dict(run["snapshot"])
                previous["report_run_label"] = f"EXECUÇÃO {run['run_no']} · {_time(run['captured_at'])}"
                previous["report_run_no"] = run["run_no"]
                report_cases.append(previous)
        current = dict(case)
        current["report_run_label"] = (f"EXECUÇÃO {len(case['previous_runs']) + 1} · ATUAL"
                                       if include_history else "")
        current["report_run_no"] = len(case["previous_runs"]) + 1
        report_cases.append(current)
    font = _font()
    styles = {
        "title": ParagraphStyle("report-title", fontName=font, fontSize=22, leading=27, textColor=INK, spaceAfter=5),
        "subtitle": ParagraphStyle("report-subtitle", fontName=font, fontSize=8, leading=12, textColor=MUTED),
        "case": ParagraphStyle("case-name", fontName=font, fontSize=14, leading=19, textColor=INK),
        "body": ParagraphStyle("report-body", fontName=font, fontSize=8.5, leading=12, textColor=INK,
                               spaceAfter=5, splitLongWords=1),
        "small": ParagraphStyle("report-small", fontName=font, fontSize=7.5, leading=10, textColor=MUTED,
                                spaceAfter=4, splitLongWords=1),
        "eyebrow": ParagraphStyle("report-eyebrow", fontName=font, fontSize=7.5, leading=10,
                                  textColor=MUTED, spaceBefore=5, spaceAfter=4),
        "caption": ParagraphStyle("report-caption", fontName=font, fontSize=7.5, leading=11,
                                  textColor=MUTED, spaceBefore=3, spaceAfter=2),
        "white": ParagraphStyle("report-white", fontName=font, fontSize=8, leading=12, textColor=colors.white),
        "brand": ParagraphStyle("report-brand", fontName=font, fontSize=19, leading=23, textColor=colors.white),
        "brand-small": ParagraphStyle("report-brand-small", fontName=font, fontSize=8, leading=12,
                                      textColor=colors.HexColor("#C2CBD5")),
        "brand-id": ParagraphStyle("report-brand-id", fontName=font, fontSize=8, leading=12,
                                   textColor=colors.HexColor("#D3DBE5"), alignment=2),
        "brand-label": ParagraphStyle("report-brand-label", fontName=font, fontSize=8, leading=12,
                                      textColor=colors.HexColor("#8BE3E2"), alignment=2),
    }
    meta = session["meta"]
    state = "Concluída" if meta.get("state") == "concluida" else "Em andamento"
    brand_name = Paragraph('Test<font color="#76DBDA">AíZé</font>', styles["brand"])
    brand_copy = Table([[brand_name], [_text("Execução de Casos de Teste", styles["brand-small"])]],
                       colWidths=[106 * mm])
    brand_copy.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    logo = Image(str(Path(__file__).resolve().parent / "static" / "report-logo.png"),
                 width=12 * mm, height=9.5 * mm)
    logo_box = Table([[logo]], colWidths=[14 * mm], rowHeights=[14 * mm])
    logo_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.white),
                                  ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 1 * mm),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 1 * mm)]))
    brand = Table([[logo_box, brand_copy,
                    Table([[_text("RELATÓRIO DE FALHA" if report_kind == "failure" else "RELATÓRIO DE EXECUÇÃO",
                                  styles["brand-label"])],
                           [_text(f"Sessão {meta['id'][:8]}", styles["brand-id"])]], colWidths=[52 * mm])]],
                  colWidths=[20 * mm, 110 * mm, 60 * mm])
    brand.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#14171D")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LEFTPADDING", (0, 0), (0, 0), 8),
                               ("LEFTPADDING", (1, 0), (1, 0), 0),
                               ("LEFTPADDING", (2, 0), (2, 0), 2),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                               ("TOPPADDING", (0, 0), (-1, -1), 13),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 13)]))
    title = _text("Relatório de Falha" if report_kind == "failure" else "Relatório de Execução", styles["title"])
    state_style = ParagraphStyle("report-state", parent=styles["small"],
                                 textColor=colors.HexColor("#9F6303" if state == "Em andamento" else "#117448"))
    state_tag = Table([[_text(state, state_style)]], colWidths=[30 * mm])
    state_tag.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1),
                                   colors.HexColor("#FFF1D8" if state == "Em andamento" else "#E1F7EC")),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 7),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    heading = Table([[title, state_tag]], colWidths=[160 * mm, 30 * mm])
    heading.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story = [brand, Spacer(1, 7 * mm), heading,
             _text(f"{meta.get('source_name', '')}  ·  {len(report_cases)} execução(ões)", styles["subtitle"]),
             Spacer(1, 5 * mm)]

    def stat(label: str, value: str, large: bool = False):
        card = Table([[_text(label.upper(), styles["eyebrow"])],
                      [_text(value, styles["case"] if large else styles["body"])]], colWidths=[60 * mm])
        card.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL),
                                  ("BOX", (0, 0), (-1, -1), .5, LINE),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                  ("TOPPADDING", (0, 0), (-1, -1), 6),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        return card

    overview = Table([[stat("Casos no relatório", str(len(chosen)), True), "",
                       stat("Início da sessão", _time(meta.get("created_at"))), "",
                       stat("Gerado em", _time(now()))]],
                     colWidths=[60 * mm, 5 * mm, 60 * mm, 5 * mm, 60 * mm])
    overview.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.extend([overview, Spacer(1, 5 * mm), _text("DISTRIBUIÇÃO DOS RESULTADOS", styles["eyebrow"])])
    order = ("aprovado", "reprovado", "bloqueado", "em_andamento", "nao_executado")
    cells = []
    for status in order:
        count = sum(case["status"] == status for case in chosen)
        percent = round(count / len(chosen) * 100)
        card = Table([[_text(str(count), styles["case"]), _text(f"{percent}%", styles["small"])],
                      [_text(LABELS[status], styles["small"]), ""]], colWidths=[21 * mm, 15 * mm])
        card.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1),
                                  colors.HexColor("#FFF1F3") if status == "reprovado" else PANEL),
                                  ("BOX", (0, 0), (-1, -1), .5, LINE),
                                  ("LINEABOVE", (0, 0), (-1, 0), 2, colors.HexColor(STATUS_COLORS[status])),
                                  ("SPAN", (0, 1), (1, 1)),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 7),
                                  ("TOPPADDING", (0, 0), (-1, 0), 7),
                                  ("BOTTOMPADDING", (0, -1), (-1, -1), 7)]))
        cells.append(card)
    counts_table = Table([[cells[0], "", cells[1], "", cells[2], "", cells[3], "", cells[4]]],
                         colWidths=[36 * mm, 2.5 * mm, 36 * mm, 2.5 * mm, 36 * mm,
                                    2.5 * mm, 36 * mm, 2.5 * mm, 36 * mm])
    counts_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                      ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.extend([counts_table, Spacer(1, 6 * mm)])

    attachment_positions: dict = {}
    attachment_records: list[dict] = []
    for case in report_cases:
        accent = colors.HexColor(STATUS_COLORS[case["status"]])
        case_label = _text(f"CASO {case['position']:02d}  {case['report_run_label']}",
                           ParagraphStyle("case-id", parent=styles["eyebrow"], textColor=TEAL))
        case_name = _text(case["name"], styles["case"])
        case_meta = _text(f"Pasta: {case['folder'] or 'Sem pasta'}\n"
                          f"Prioridade: {case['priority'] or 'Não informada'}  ·  "
                          f"Status importado: {case['source_status'] or 'Não informado'}", styles["small"])
        case_header = Table([[case_label, _text(LABELS[case["status"]], styles["small"])],
                             [case_name, ""], [case_meta, ""]], colWidths=[155 * mm, 35 * mm])
        case_header.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FBFD")),
                                         ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
                                         ("BOX", (0, 0), (-1, -1), .5, LINE),
                                         ("SPAN", (0, 1), (1, 1)), ("SPAN", (0, 2), (1, 2)),
                                         ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 12),
                                         ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                                         ("TOPPADDING", (0, 0), (-1, 0), 6),
                                         ("BOTTOMPADDING", (0, -1), (-1, -1), 7)]))
        story.extend([case_header, Spacer(1, 3 * mm)])
        precondition = Table([[_text("PRÉ-CONDIÇÕES", ParagraphStyle(
            "pre-label", parent=styles["eyebrow"], textColor=TEAL)),
            _text(case["precondition"], styles["body"], "Não informado")]],
            colWidths=[33 * mm, 157 * mm])
        precondition.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EBF8F8")),
                                          ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                          ("LEFTPADDING", (0, 0), (-1, -1), 9),
                                          ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                                          ("TOPPADDING", (0, 0), (-1, -1), 8),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        story.extend([precondition, Spacer(1, 2 * mm)])
        story.extend(_rich_section("Anotações e evidências nas pré-condições",
                                   case["precondition_notes_blocks"], directory, styles))
        failed_count = sum(step["status"] == "reprovado" for step in case["steps"])
        story.append(_text(f"PASSOS DO CASO  ·  {len(case['steps'])} passos  ·  {failed_count} reprovado(s)",
                           styles["eyebrow"]))
        for step in case["steps"]:
            step_accent = colors.HexColor(STATUS_COLORS[step["status"]])
            status_time = LABELS[step["status"]]
            if step.get("status_changed_at"):
                status_time += f"  ·  {_time(step['status_changed_at'])}"
            step_title = Table([[_text(f"PASSO {step['position']:02d}", styles["small"]),
                                 _text(status_time, styles["small"])]], colWidths=[95 * mm, 95 * mm])
            step_title.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.white),
                                            ("LINEBEFORE", (0, 0), (0, 0), 3, step_accent),
                                            ("LINEABOVE", (0, 0), (-1, 0), .5, LINE),
                                            ("LEFTPADDING", (0, 0), (-1, -1), 9),
                                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            core = [step_title, Spacer(1, 1 * mm), _text(step["action"], styles["body"])]
            fields = (("DADOS DE TESTE", step["test_data"]), ("RESULTADO ESPERADO", step["expected"]))
            fields_table = Table([[_text(label, styles["eyebrow"]) for label, _ in fields],
                                  [_text(value, styles["body"], "Não informado") for _, value in fields]],
                                 colWidths=[95 * mm, 95 * mm])
            fields_table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, LINE),
                                              ("INNERGRID", (0, 0), (-1, -1), .5, LINE),
                                              ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                              ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                              ("TOPPADDING", (0, 0), (-1, -1), 6),
                                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            core.append(fields_table)
            story.extend([Spacer(1, 2 * mm), KeepTogether(core), Spacer(1, 2 * mm)])
            story.extend(_rich_section("Resultado observado", step["actual_blocks"], directory, styles))
            if step.get("attachments"):
                story.append(_text("ARQUIVOS ANEXADOS AO PASSO", styles["eyebrow"]))
                for attachment in step["attachments"]:
                    marker = attachment["id"]
                    attachment_records.append({"marker": marker, "item": attachment,
                                               "case_position": case["position"],
                                               "run_no": case["report_run_no"],
                                               "step_position": step["position"]})
                    extension = attachment.get("extension") or attachment_extension(attachment["original_name"])
                    size_text = (f"{attachment['size']} B" if attachment["size"] < 1024
                                 else f"{attachment['size'] / 1024:.1f} KB")
                    label = f"{attachment['original_name']} · {extension or 'sem extensão'} · {size_text}"
                    story.append(AttachmentParagraph(escape(label), styles["small"], marker, attachment_positions))
            if step["comment"]:
                story.extend(_section("Comentário do passo", step["comment"], [], directory, styles))
        story.extend(_rich_section("Comentário do caso", case["comment_blocks"], directory, styles))
        story.extend([Spacer(1, 4 * mm), HRFlowable(width="100%", thickness=.6, color=LINE), Spacer(1, 7 * mm)])

    report = directory / "relatorios" / output_name
    report.parent.mkdir(parents=True, exist_ok=True)
    temporary = report.with_suffix(".pdf.tmp")
    embedded_temporary = report.with_suffix(".embedded.pdf.tmp")
    document = SimpleDocTemplate(str(temporary), pagesize=A4, rightMargin=10 * mm, leftMargin=10 * mm,
                                 topMargin=10 * mm, bottomMargin=13 * mm,
                                 title="Relatório de falha" if report_kind == "failure" else "Relatório de execução")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(10 * mm, 10 * mm, A4[0] - 10 * mm, 10 * mm)
        canvas.setFont(font, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(10 * mm, 6 * mm, "TestAíZé")
        canvas.drawRightString(A4[0] - 10 * mm, 6 * mm, f"Sessão {meta['id'][:8]}  ·  {doc.page}")
        canvas.restoreState()

    try:
        document.build(story, onFirstPage=footer, onLaterPages=footer)
        if attachment_records:
            _embed_step_files(temporary, embedded_temporary, directory, attachment_records, attachment_positions)
            os.replace(embedded_temporary, report)
        else:
            os.replace(temporary, report)
    finally:
        temporary.unlink(missing_ok=True)
        embedded_temporary.unlink(missing_ok=True)
    return report
