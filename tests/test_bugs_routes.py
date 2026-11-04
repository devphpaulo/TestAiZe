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
        fields = dict(title='Bug <script>alert(1)</script>', severity='Crítica', actual='Obtido', expected='Esperado',
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
