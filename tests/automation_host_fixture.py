"""Real Flask host for the Node integration gate, with an ownership pipe."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from werkzeug.serving import make_server
from testplayer.web import create_app
from testplayer.storage import create_draft
import os

app = create_app(Path(sys.argv[1]))
if os.environ.get('TESTAIZE_MANUAL_FIXTURE') == '1':
    source = Path(sys.argv[1]) / 'temporarios' / 'visual.csv'
    source.write_text('fixture', encoding='utf-8')
    parsed = {'sha256': 'visual-fixture', 'sheets': [{'name': 'Casos', 'cases': [
        {'sheet': 'Casos', 'row': 2, 'name': 'Caso visual', 'precondition': '', 'source_status': '', 'priority': 'Normal', 'folder': 'Manual/Ciclo',
         'steps': [{'action': 'Verificar campo de busca', 'test_data': '', 'expected': 'Sem transbordamento'}]}
    ]}]}
    manual_id = create_draft(Path(sys.argv[1]), parsed, source, {'Casos'})
    print('MANUAL_READY ' + manual_id, flush=True)
server = make_server("127.0.0.1", 0, app, threaded=True)
threading.Thread(target=server.serve_forever, daemon=True).start()
print(f"HOST_READY http://127.0.0.1:{server.server_port}", flush=True)
try:
    sys.stdin.readline()
finally:
    app.extensions['automation_suite'].shutdown()
    app.extensions["automation_recorder"].shutdown()
    server.shutdown()
