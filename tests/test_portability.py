"""Credential location and pinned-source regression checks without network access."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from robot_agent_eval import common
from robot_agent_eval.snapshots import fetch_snapshots


class Portability(unittest.TestCase):
    def test_environment_credential_precedes_file_and_relative_file_uses_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'key.json').write_text(json.dumps({'provider': 'fixture-only'}))
            config = dict(api_key_file='key.json', api_key_json_field='provider')
            with patch.object(common, 'ROOT', root), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(common.key(config), 'fixture-only')
                with patch.dict(os.environ, OPENAI_API_KEY='environment-fixture'):
                    self.assertEqual(common.key(dict(api_key_file='missing')), 'environment-fixture')

    def test_source_restore_uses_locked_revision_and_validates_archive_checksum(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('upstream-locked/module.py', 'VALUE = 1\n')
        payload = archive.getvalue()
        for digest, expected_status in [(hashlib.sha256(payload).hexdigest(), 'snapshot_fetched'),
                                        ('0' * 64, 'fetch_failed')]:
            with self.subTest(expected_status=expected_status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root/'source-lock.json').write_text(json.dumps({'astra_policy': dict(
                    repo='anonymous-report-421/eval-of-gpt-6-astra-as-policy', revision='locked-revision',
                    archive_sha256=digest, status='snapshot_fetched', path='/old/workstation/snapshot')}))
                with patch('robot_agent_eval.snapshots.request', return_value=io.BytesIO(payload)) as request:
                    result = fetch_snapshots(root, jobs=1, names=['astra_policy'])
                self.assertEqual(result['astra_policy']['status'], expected_status)
                self.assertEqual(request.call_count, 1)
                self.assertTrue(request.call_args.args[0].endswith('/zip/locked-revision'))
                target = root/'source-snapshots/astra_policy/module.py'
                self.assertEqual(target.exists(), expected_status == 'snapshot_fetched')
                if target.exists():
                    with patch('robot_agent_eval.snapshots.request') as request:
                        cached = fetch_snapshots(root, jobs=1, names=['astra_policy'])
                    request.assert_not_called()
                    self.assertEqual(cached['astra_policy']['revision'], 'locked-revision')


if __name__ == '__main__':
    unittest.main()
