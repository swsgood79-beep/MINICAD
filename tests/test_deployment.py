import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from server import app

class DeploymentTest(unittest.TestCase):
    def test_private_site_requires_login(self):
        with patch.dict(os.environ, {'MINICAD_DEPLOYED':'1', 'MINICAD_USERNAME':'operator', 'MINICAD_PASSWORD':'test-only-password'}):
            with TestClient(app) as client:
                self.assertEqual(client.get('/healthz').status_code,200)
                for path in ('/','/api/status','/api/export/dxf','/docs','/assets/test.js'):
                    self.assertEqual(client.get(path).status_code,401)
                self.assertEqual(client.post('/api/open').status_code,401)
                self.assertEqual(client.get('/api/status',auth=('operator','wrong')).status_code,401)
                r=client.get('/api/status',auth=('operator','test-only-password'))
                self.assertEqual(r.status_code,200)
                self.assertEqual(r.json()['mode'],'private-hosted')
                self.assertEqual(r.headers['cache-control'],'no-store')
                self.assertEqual(r.headers['x-content-type-options'],'nosniff')
                self.assertEqual(client.get('/',auth=('operator','test-only-password')).status_code,200)

    def test_bad_authorization_is_rejected(self):
        with patch.dict(os.environ,{'MINICAD_USERNAME':'operator','MINICAD_PASSWORD':'test-only-password'}):
            with TestClient(app) as client:
                for header in ('Basic invalid!','Basic YQ==','Bearer token','Basic //8='):
                    self.assertEqual(client.get('/api/status',headers={'Authorization':header}).status_code,401)

    def test_hosted_mode_fails_closed_without_password(self):
        with patch.dict(os.environ,{'MINICAD_DEPLOYED':'1','MINICAD_USERNAME':'operator','MINICAD_PASSWORD':''}):
            with self.assertRaisesRegex(RuntimeError,'requires MINICAD_USERNAME'):
                with TestClient(app):
                    pass

if __name__=='__main__':
    unittest.main()
