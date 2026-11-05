import io
import json
import unittest
from test_bugs_flow import BugsFixture
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
