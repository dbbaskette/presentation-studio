"""Drive access through gcloud: a link read as a file ID, and a Doc exported as text, with
the token kept out of every refusal. Nothing here starts gcloud or reaches the network."""
import unittest
from unittest import mock

import helpers  # noqa: F401
import gdrive
from workspace import WorkspaceError


class FileIdTests(unittest.TestCase):
    def test_url_and_bare_id(self):
        url = 'https://docs.google.com/document/d/1AbC_d-9/edit?usp=sharing'
        self.assertEqual(gdrive.file_id(url), '1AbC_d-9')
        self.assertEqual(gdrive.file_id('1AbC_d-9'), '1AbC_d-9')

    def test_not_a_link(self):
        with self.assertRaises(WorkspaceError):
            gdrive.file_id('https://example.com/x')


class ExportTests(unittest.TestCase):
    def test_token_never_in_an_error(self):
        run = mock.Mock(return_value=mock.Mock(returncode=0, stdout='SECRET\n'))
        def refuse(request, timeout=None):
            raise OSError('failed with SECRET')
        drive = gdrive.Drive(run=run, urlopen=refuse)
        with self.assertRaises(WorkspaceError) as caught:
            drive.export_text('abc')
        self.assertNotIn('SECRET', str(caught.exception))

    def test_a_doc_is_asked_for_as_plain_text_with_the_token(self):
        run = mock.Mock(return_value=mock.Mock(returncode=0, stdout='SECRET\n'))
        asked = []

        def answer(request, timeout=None):
            asked.append(request)
            reply = mock.MagicMock()
            reply.__enter__.return_value.read.return_value = 'Rolling restarts\n'.encode()
            return reply
        text = gdrive.Drive(run=run, urlopen=answer).export_text('1AbC_d-9')
        self.assertEqual(text, 'Rolling restarts\n')
        self.assertEqual(asked[0].full_url, 'https://www.googleapis.com/drive/v3/files/'
                                            '1AbC_d-9/export?mimeType=text%2Fplain')
        self.assertEqual(asked[0].get_header('Authorization'), 'Bearer SECRET')

    def test_no_sign_in_is_said_plainly(self):
        run = mock.Mock(return_value=mock.Mock(returncode=1, stdout=''))
        with self.assertRaisesRegex(WorkspaceError, 'gcloud auth login'):
            gdrive.Drive(run=run, urlopen=mock.Mock()).export_text('abc')


if __name__ == '__main__':
    unittest.main()
