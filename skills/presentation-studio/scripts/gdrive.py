"""Google Drive, reached through the gcloud command: a Google Doc read as plain text.

What a caller needs to know
---------------------------
    gdrive.file_id(link)                 # the Drive ID in a link, or a bare ID as it is
    gdrive.Drive().export_text(file_id)  # a Google Doc's text

- `file_id` takes a bare ID or an address of the form https://docs.google.com/.../d/<id>/...
  and refuses anything else with WorkspaceError and a sentence.
- `Drive(run=None, urlopen=None)` asks `gcloud auth print-access-token` once for an access
  token and uses the Drive v3 API: `files/<id>/export?mimeType=text/plain`. The token is held
  in memory for the life of the object and goes only into the Authorization header. It is
  never written, printed or put in a refusal.
- Every failure is a WorkspaceError with a sentence for a person: gcloud missing or not
  signed in, the Doc not found, Drive refusing, or the network.
"""
from __future__ import annotations

import http.client
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from workspace import WorkspaceError

FILE_ID = re.compile(r'^[A-Za-z0-9_-]+$')
LINK = re.compile(r'^https://docs\.google\.com/(?:[\w.-]+/)*d/([A-Za-z0-9_-]+)(?:[/?#].*)?$')
FILES = 'https://www.googleapis.com/drive/v3/files'
SIGN_IN = 'gcloud auth login --enable-gdrive-access'
TIMEOUT = 60


def file_id(link: str) -> str:
    """The Drive ID a link names, or a bare ID as it is."""
    text = link.strip() if isinstance(link, str) else ''
    if FILE_ID.match(text):
        return text
    found = LINK.match(text)
    if found:
        return found.group(1)
    raise WorkspaceError('That is not a link to a Google Doc or Slides file. Copy the link '
                         'from the file\'s Share button and try again.')


class Drive:
    """The Drive v3 REST API over urllib, signed in through the gcloud command."""

    def __init__(self, run=None, urlopen=None):
        self._run = run or subprocess.run
        self._urlopen = urlopen or urllib.request.urlopen
        self._token = None

    def export_text(self, file_id: str) -> str:
        """A Google Doc's content as plain text."""
        if not isinstance(file_id, str) or not FILE_ID.match(file_id):
            raise WorkspaceError('That is not the ID of a file in Google Drive.')
        reply = self._send(f'{FILES}/{urllib.parse.quote(file_id, safe="")}/export?'
                           + urllib.parse.urlencode({'mimeType': 'text/plain'}))
        try:
            return reply.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise WorkspaceError("Google's export of the Doc was not readable text. "
                                 'Try again.') from None

    def _access_token(self) -> str:
        if self._token is None:
            try:
                done = self._run(['gcloud', 'auth', 'print-access-token'], capture_output=True,
                                 text=True, timeout=TIMEOUT)
            except FileNotFoundError:
                raise WorkspaceError('The gcloud command was not found. Install the Google '
                                     f'Cloud CLI and run `{SIGN_IN}`.') from None
            except (OSError, subprocess.SubprocessError):
                raise WorkspaceError(f'The gcloud command did not answer. Run `{SIGN_IN}` '
                                     'and try again.') from None
            # Nothing gcloud printed is repeated: its output is where the token is.
            token = (done.stdout or '').strip() if done.returncode == 0 else ''
            if not token or len(token.split()) != 1:
                raise WorkspaceError('gcloud has no signed-in account it can give access '
                                     f'for. Run `{SIGN_IN}` and try again.')
            self._token = token
        return self._token

    def _send(self, url: str) -> bytes:
        token = self._access_token()
        request = urllib.request.Request(url, method='GET')
        request.add_header('Authorization', f'Bearer {token}')
        try:
            with self._urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as failure:
            refusal = self._explain(failure)
        except (OSError, http.client.HTTPException) as failure:
            reason = getattr(failure, 'reason', None) or failure
            refusal = (f'Could not reach Google Drive ({reason}). Check the connection and '
                       'try again.')
        raise WorkspaceError(refusal.replace(token, '[token]')) from None

    @staticmethod
    def _explain(failure: urllib.error.HTTPError) -> str:
        """What an HTTP error from Drive means and what to do about it."""
        try:
            detail = json.loads(failure.read().decode('utf-8', 'replace'))['error']['message']
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            detail = failure.reason
        finally:
            failure.close()
        detail = ' '.join(str(detail or '').split())[:300].rstrip('.')
        if failure.code == 401:
            return f'Google did not accept the gcloud sign-in. Run `{SIGN_IN}` and try again.'
        if failure.code == 403 and 'scope' in detail.lower():
            return ('The gcloud sign-in does not include Google Drive. '
                    f'Run `{SIGN_IN}` and try again.')
        if failure.code == 404:
            return ('Google could not find the Doc. It may have been deleted, or the signed-in '
                    'account cannot open it.')
        if failure.code == 403:
            return (f'Google Drive refused the request (HTTP 403: {detail}). Check that the '
                    f'signed-in account may open the Doc, or run `{SIGN_IN}`.')
        return f'Google Drive answered HTTP {failure.code} ({detail}). Try again shortly.'
