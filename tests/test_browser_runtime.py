import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ezdxf
import browser_runtime as runtime
from test_api import fixture

class BrowserRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        # Browser paths are confined to its virtual filesystem; redirect for native tests.
        self.source=Path(self.temp.name)/'input.dxf'
        self.original_path=runtime.Path
        self.patcher=patch('browser_runtime.Path',side_effect=lambda p:self.source if p=='/tmp/minicad-input.dxf' else Path(p))
        self.patcher.start()
        raw,self.ids=fixture();self.raw=raw;self.source.write_bytes(raw)
        opened=runtime.dispatch('/api/open',{},filename='test.dxf')
        self.key=opened['document_id']
    def tearDown(self):
        runtime.session=None;runtime.session_id=None
        self.patcher.stop();self.temp.cleanup()
    def test_browser_history_and_original_document_preservation(self):
        runtime.dispatch('/api/edit',dict(op='move',handles=self.ids[:2],dx=10,dy=5),self.key)
        self.assertEqual(runtime.session.doc.entitydb[self.ids[0]].dxf.start,(10,5,0))
        runtime.dispatch('/api/history/undo',{},self.key)
        self.assertEqual(runtime.session.doc.entitydb[self.ids[0]].dxf.start,(0,0,0))
        runtime.dispatch('/api/history/redo',{},self.key)
        self.assertEqual(runtime.session.doc.entitydb[self.ids[1]].dxf.center,(60,45,0))
        self.assertEqual(runtime.session.doc.entitydb[self.ids[6]].dxftype(),'SPLINE')
        self.assertEqual(len(runtime.session.doc.modelspace().query('DIMENSION')),1)
    def test_close_old_document_does_not_close_replacement(self):
        self.source.write_bytes(self.raw)
        other=runtime.dispatch('/api/open',{},filename='second.dxf')['document_id']
        runtime.dispatch('/api/document',{},self.key)
        self.assertEqual(runtime.session_id,other)
        runtime.dispatch('/api/document',{},other)
        self.assertIsNone(runtime.session)
    def test_invalid_inputs_are_errors_without_mutation(self):
        for data in [dict(op='add_circle',radius=0),dict(op='move',dx=float('nan')),dict(op='invalid')]:
            response=json.loads(runtime.dispatch_json('/api/edit',json.dumps(data),self.key,''))
            self.assertEqual(response['status'],422)
        with self.assertRaisesRegex(ValueError,'DXF'):
            runtime.dispatch('/api/open',{},filename='file.dwg')
        self.assertEqual(runtime.session.revision,0)
    def test_dwg_screen_edit_works_but_file_exports_are_blocked(self):
        self.source.write_bytes(self.raw)
        opened=runtime.dispatch('/api/open-dwg',{},filename='original.dwg')
        key=opened['document_id']
        self.assertEqual(opened['source_format'],'dwg')
        self.assertEqual(opened['filename'],'original.dwg')
        self.assertTrue(any('DWG 시험' in w for w in opened['warnings']))
        edited=runtime.dispatch('/api/edit',dict(op='move',handle=self.ids[0],dx=10),key)
        self.assertEqual(edited['source_format'],'dwg')
        self.assertEqual(edited['filename'],'original.dwg')
        self.assertEqual(runtime.session.doc.entitydb[self.ids[0]].dxf.start,(10,0,0))
        for format in ('dxf','dwg'):
            response=json.loads(runtime.dispatch_json('/api/export/'+format,'{}',key,''))
            self.assertEqual(response['status'],400)
        runtime.dispatch('/api/history/undo',{},key)
        self.assertEqual(runtime.session.doc.entitydb[self.ids[0]].dxf.start,(0,0,0))

    def test_failed_open_preserves_previous_document(self):
        self.source.write_bytes(b'not a DXF')
        response=json.loads(runtime.dispatch_json('/api/open','{}',None,'bad.dxf'))
        self.assertEqual(response['status'],422)
        self.assertEqual(runtime.session_id,self.key)
        self.assertEqual(runtime.session.doc.entitydb[self.ids[0]].dxftype(),'LINE')

if __name__=='__main__':unittest.main()
