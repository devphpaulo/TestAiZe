"""Self-contained bug report snapshot; browser rendering runs without the root lock."""
import base64
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .bugs_coordinator import coordinated
from .pdf_export import render_html_to_pdf


def render_bug_html(service, bug_id):
    from .storage import find_directory, read_session
    with coordinated(service.root):
        bug = service.get(bug_id)
        images = {}
        for item in bug['evidence']:
            if item['relative_path']:
                content, mime = service.evidence_bytes(bug_id, item['id'])
                images[item['id']] = f'data:{mime};base64,' + base64.b64encode(content).decode('ascii')
        blocks = json.loads(bug['description_doc'])
        for block in blocks:
            if block['type'] == 'image' and block['id'] not in images:
                raise ValueError('Documento referencia uma evidência ausente.')
        for link in bug['links']:
            directory = find_directory(service.root, link['session_id'])
            case = None
            if directory:
                case = next((c for c in read_session(directory)['cases'] if c['id'] == link['case_id']), None)
            link['name'] = case['name'] if case else 'Sessão/caso indisponível'
    environment = Environment(loader=FileSystemLoader(Path(__file__).parent / 'templates'),
                              autoescape=select_autoescape(['html']))
    return environment.get_template('bug_report.html').render(bug=bug, blocks=blocks, images=images)


def generate_bug_pdf(service, bug_id):
    html = render_bug_html(service, bug_id)
    return render_html_to_pdf(html, service.root / 'bugs' / bug_id / 'relatorios' / 'bug.pdf')
