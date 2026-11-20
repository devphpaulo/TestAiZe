import io
import json
import unittest
from test_bugs_flow import BugsFixture
from testplayer.bugs_service import MAX_BUG_FILE_BYTES
from testplayer.web import create_app


class BugsRoutesTests(BugsFixture, unittest.TestCase):
    # Reuse the synthetic session fixture, not the inherited acceptance suite.
    def setUp(self):
        super().setUp()
        self.app = create_app(self.root)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['csrf_token'] = 'test-token'
        self.headers = {'X-CSRF-Token': 'test-token'}

    def test_shared_header_has_board_select_and_one_appearance_control(self):
        for url in ('/', '/bugs', f'/sessao/{self.sid}'):
            html = self.client.get(url).get_data(as_text=True)
            header = html.split('<header class="topbar">')[1].split('</nav>')[0]
            self.assertIn('id="board-select"', header)
            self.assertIn('id="appearance-trigger"', header)
            self.assertNotIn('Nesta máquina', header)
            self.assertNotIn('id="theme-toggle"', header)
            self.assertNotIn('id="accent-trigger"', header)
            self.assertIn('<option value="" selected disabled hidden>Quadros</option>', header)

    def test_http_create_player_and_board(self):
        fields = dict(title='Bug <script>alert(1)</script>', severity='Bloqueador', actual='Obtido', expected='Esperado',
                      blocks=[{'type': 'text', 'text': 'Passos'}, {'type': 'image', 'id': 'img', 'width': 50}])
        response = self.client.post(f'/api/sessao/{self.sid}/bugs', headers=self.headers,
                                    data={'document': json.dumps(fields), 'img': (io.BytesIO(self.image), 'image.png')})
        self.assertEqual(response.status_code, 201, response.data)
        bug = response.json['bug']
        for url in ('/bugs', f'/bugs/{bug["id"]}?session_id={self.sid}', f'/sessao/{self.sid}/bugs',
                    f'/sessao/{self.sid}/bugs/novo', f'/sessao/{self.sid}'):
            result = self.client.get(url)
            self.assertEqual(result.status_code, 200, (url, result.data[:500]))
        detail = self.client.get(f'/bugs/{bug["id"]}').get_data(as_text=True)
        self.assertNotIn('<script>alert(1)</script>', detail)
        self.assertEqual(self.client.get(f'/bugs/{bug["id"]}/evidencias/{bug["evidence"][0]["id"]}').data, self.image)

    def test_severity_select_and_linked_case_current_status(self):
        from testplayer import storage
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        storage.save_result(self.directory, 1, 'reprovado', 'Falhou')
        page = self.client.get(f'/bugs/{bug["id"]}?session_id={self.sid}').get_data(as_text=True)
        self.assertIn('<select name="severity"', page)
        for code in ('baixa', 'media', 'alta', 'bloqueador'):
            self.assertIn(f'value="{code}"', page)
        self.assertIn('Caso 1', page)
        self.assertIn('data-case-status="reprovado"', page)
        self.assertNotIn('Nenhuma prova de reteste.', page)
        self.assertNotIn('Sem vínculos.', page)
        invalid = self.client.post(f'/api/bugs/{bug["id"]}', headers=self.headers,
                                   json=dict(bug, severity='arbitrária', blocks=json.loads(bug['description_doc'])))
        self.assertEqual(invalid.status_code, 422)

    def test_bug_attachments_replace_with_save_and_download_as_files(self):
        from testplayer.bugs_export import render_bug_html

        fields = dict(title='Bug com arquivo', severity='alta', actual='Obtido', expected='Esperado',
                      blocks=[{'type': 'text', 'text': 'Passos'}])
        url = f'/api/sessao/{self.sid}/bugs'
        names = ['caso.PDF', 'execução.log', 'texto.txt', 'massa.xml', 'resposta.json', 'dados.xlsx', 'legado.xls', 'tabela.csv']
        files = {str(index): (io.BytesIO(name.encode()), name) for index, name in enumerate(names)}
        response = self.client.post(url, headers=self.headers, data={'document': json.dumps(fields), **files})
        self.assertEqual(response.status_code, 201, response.data)
        bug = response.json['bug']
        self.assertCountEqual([item['original_name'] for item in bug['evidence']], names)
        for item in bug['evidence']:
            with self.client.get(f'/bugs/{bug["id"]}/evidencias/{item["id"]}') as download:
                self.assertEqual(download.data, item['original_name'].encode())
                self.assertEqual(download.mimetype, 'application/octet-stream')
                self.assertTrue(download.headers['Content-Disposition'].startswith('attachment;'))
                self.assertEqual(download.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn('resposta.json', render_bug_html(self.service, bug['id']))
        edit_url = f'/api/bugs/{bug["id"]}'
        invalid = self.client.post(edit_url, headers=self.headers, json=dict(fields, attachment_ids=[]))
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(len(self.service.get(bug['id'])['evidence']), len(names))
        replace = self.client.post(edit_url, headers=self.headers, data={
            'document': json.dumps(dict(fields, attachment_ids=['novo'])),
            'novo': (io.BytesIO(b'novo'), 'novo.log'),
        })
        self.assertEqual(replace.status_code, 200, replace.data)
        self.assertEqual([item['original_name'] for item in replace.json['bug']['evidence']], ['novo.log'])

    def test_bug_attachment_limit_is_per_file_and_invalid_types_are_rejected(self):
        url = f'/api/sessao/{self.sid}/bugs'
        document = json.dumps(dict(title='Bug', severity='alta', actual='Obtido', expected='Esperado',
                                   blocks=[{'type': 'text', 'text': 'Passos'}]))
        for name, data in [('setup.exe', b'arquivo'), ('excedente.log', b'x' * (MAX_BUG_FILE_BYTES + 1))]:
            with self.subTest(name=name):
                result = self.client.post(url, headers=self.headers,
                                          data={'document': document, 'arquivo': (io.BytesIO(data), name)})
                self.assertEqual(result.status_code, 422, result.data)
        self.assertEqual(self.service.list(), [])
        valid = self.client.post(url, headers=self.headers, data={
            'document': document,
            **{str(i): (io.BytesIO(b'x' * MAX_BUG_FILE_BYTES), f'{i}.log') for i in range(3)},
        })
        self.assertEqual(valid.status_code, 201, valid.data)
        self.assertEqual(len(valid.json['bug']['evidence']), 3)

    def test_linked_names_and_statuses_are_resolved_per_execution(self):
        from testplayer import storage
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        completed = storage.finalize(self.root, self.directory)
        new_id = storage.rerun(self.root, completed)
        directory = storage.find_directory(self.root, new_id)
        with storage.db(directory) as db:
            with db:
                db.execute("UPDATE cases SET name='Mesmo ID, outra execução',manual_status='reprovado' WHERE id=1")
        self.service.link(bug['id'], new_id, [1])
        links = {link['session_id']: link for link in self.service.detail(bug['id'])['links']}
        self.assertEqual((links[self.sid]['name'], links[self.sid]['status']), ('Caso 1', 'bloqueado'))
        self.assertEqual((links[new_id]['name'], links[new_id]['status']), ('Mesmo ID, outra execução', 'reprovado'))

    def test_severity_accepts_only_the_four_choices_without_rewriting_old_records(self):
        bug = self.create_bug()
        for value, expected in [('Baixa', 'baixa'), ('Média', 'media'), ('Alta', 'alta'), ('Bloqueador', 'bloqueador')]:
            fields = dict(bug, severity=value, blocks=json.loads(bug['description_doc']))
            self.assertEqual(self.service.edit(bug['id'], fields)['severity'], expected)
        with self.service.store.connect() as db:
            db.execute("UPDATE bugs SET severity='Legada' WHERE id=?", (bug['id'],))
        self.assertEqual(self.service.get(bug['id'])['severity'], 'Legada')

    def test_image_restore_upload_does_not_cross_execution_generation(self):
        from testplayer import storage
        storage.start_case_run(self.directory, 1)
        routes = [f'/api/sessao/{self.sid}/passo/1/imagem',
                  f'/api/sessao/{self.sid}/caso/1/evidencia/precondition',
                  f'/api/sessao/{self.sid}/caso/1/evidencia/comment']
        for route in routes:
            response = self.client.post(route, headers=self.headers,
                                        data={'imagem': (io.BytesIO(self.image), 'restored.png'),
                                              'expected_generation': 'generation'})
            self.assertEqual(response.status_code, 409, (route, response.data))
        record = storage.read_session(self.directory)
        self.assertEqual(record['cases'][0]['steps'][0]['evidence'], [])
        self.assertEqual(record['cases'][0]['precondition_evidence'], [])

    def test_http_security_status_and_contract(self):
        bug = self.create_bug()
        url = f'/api/bugs/{bug["id"]}/sessao/{self.sid}/vinculos'
        self.assertEqual(self.client.post(url, json={'case_ids': [1]}).status_code, 400)
        self.assertEqual(self.client.post(url, json={'case_ids': [1]}, headers=self.headers | {'Origin': 'https://evil.test'}).status_code, 403)
        self.assertEqual(self.client.post(url, json={'case_ids': [1, 999]}, headers=self.headers).status_code, 422)
        self.assertEqual(self.service.get(bug['id'])['links'], [])
        self.assertEqual(self.client.post(url, json={'case_ids': [1, 2]}, headers=self.headers).status_code, 200)
        case_url = f'/api/sessao/{self.sid}/caso/1'
        response = self.client.post(case_url, json={'status': '', 'comment': 'legacy'}, headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['manual_status'], 'bloqueado')
        from testplayer.storage import read_session
        self.assertEqual(read_session(self.directory)['cases'][0]['comment'], 'legacy')
        self.assertEqual(self.client.post(case_url + '/status', json={'status': []}, headers=self.headers).status_code, 422)
        response = self.client.post(case_url, json={'comment': 'Comentário'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        state = response.json
        response = self.client.post(case_url + '/status', headers=self.headers,
                                    json={'status': 'aprovado', 'expected_revision': state['status_revision'],
                                          'expected_generation': state['execution_generation']})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.post(f'/api/bugs/{bug["id"]}/estado', headers=self.headers,
                                         json={'target': 'finalizado', 'expected_state': 'aberto'}).status_code, 409)
