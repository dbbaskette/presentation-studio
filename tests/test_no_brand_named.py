"""Presentation Studio is for any brand: the brand skill, and the repository it is installed
from, are the person's own. No file Presentation Studio keeps in git names a particular
brand, in its code, its tests, its stand-ins or its documents. The tests use a made-up
brand, Acme.

The names looked for are written below with an escape, so that this file does not name
them either.
"""
import re
import shutil
import subprocess
import unittest

import helpers

# The brands of the stand-in Presentation Studio was first made for, which it must not name.
NAMED = re.compile(r'(?i)t\x61nzu|vmw\x61re|bro\x61dcom')


@unittest.skipUnless(shutil.which('git') and (helpers.REPO / '.git').exists(),
                     'only a copy of the repository has its files listed by git')
class NoBrandNamedTests(unittest.TestCase):
    def test_no_tracked_file_names_a_brand(self):
        listed = subprocess.run(['git', 'ls-files', '-z'], cwd=helpers.REPO, check=True,
                                capture_output=True).stdout.split(b'\0')
        found = []
        for name in filter(None, listed):
            path = helpers.REPO / name.decode('utf-8', 'surrogateescape')
            try:
                data = path.read_bytes()
            except OSError:   # listed, but removed from the working tree
                continue
            if b'\0' in data[:8000]:   # a binary file, as git tells one
                continue
            text = data.decode('utf-8', 'replace')
            found += [f'{path.relative_to(helpers.REPO)}:{number}: {line.strip()[:100]}'
                      for number, line in enumerate(text.splitlines(), 1)
                      if NAMED.search(line)]
        self.assertEqual(found, [], 'a tracked file names a brand')

    def test_the_names_are_still_recognised(self):
        self.assertTrue(NAMED.search('Run ' + 'T' + 'anzu fast'))
        self.assertFalse(NAMED.search('Run Acme fast'))


if __name__ == '__main__':
    unittest.main()
