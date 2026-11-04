from unittest.mock import patch
import unittest
from test_bugs_flow import BugsFixture
from testplayer.bugs_export import render_bug_html, generate_bug_pdf
from testplayer.storage import remove_session


class BugsPdfTests(BugsFixture, unittest.TestCase):
    def test_bug_report_survives_origin_delete_and_embeds_owned_bytes(self):
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        remove_session(self.root, self.sid, True)
        with patch('testplayer.bugs_export.read_session', create=True, side_effect=AssertionError('must not require origin')):
            html = render_bug_html(self.service, bug['id'])
        self.assertIn('data:image/png;base64,', html)
        self.assertIn('width:65%', html)
        self.assertIn('Falha &lt;script&gt;', html)
        self.assertIn('Sem vínculos disponíveis', html)
        self.assertLess(html.index('Fluxo\nPassos'), html.index('data:image/png'))
        with patch('testplayer.bugs_export.render_html_to_pdf') as render:
            generate_bug_pdf(self.service, bug['id'])
            self.assertIn('data:image/png;base64,', render.call_args.args[0])

    def test_corrupt_image_is_an_explicit_export_failure(self):
        bug = self.create_bug()
        path = self.root / 'bugs' / bug['evidence'][0]['relative_path']
        path.write_bytes(b'corrupted')
        with self.assertRaises(ValueError):
            render_bug_html(self.service, bug['id'])
