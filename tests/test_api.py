import io
import math
import unittest
from unittest.mock import patch
import ezdxf
from fastapi.testclient import TestClient
from server import app, DOCS, primitive


def fixture():
    doc = ezdxf.new('R2018')
    doc.units = 4
    doc.layers.new('visible')
    off = doc.layers.new('off'); off.off()
    locked = doc.layers.new('locked'); locked.lock()
    m = doc.modelspace()
    line = m.add_line((0, 0), (100, 0), dxfattribs={'layer':'visible'})
    circle = m.add_circle((50, 40), 10)
    arc = m.add_arc((0, 0), 10, 350, 10)
    poly = m.add_lwpolyline([(0,0,1),(20,0,0)],format='xyb')
    poly2 = m.add_polyline2d([(0,10),(20,10),(20,30)],close=True)
    text = m.add_text('테스트',dxfattribs={'insert':(20,20)})
    m.add_mtext('여러 줄\\P문자')
    spline = m.add_spline([(0,0),(5,8),(10,0)])
    m.add_line((0,0),(1,1),dxfattribs={'layer':'locked'})
    m.add_line((0,0,0),(0,0,10))
    block = doc.blocks.new('fixture'); block.add_circle((0,0),2)
    insert = m.add_blockref('fixture',(20,20))
    dim = m.add_linear_dim(base=(0,30),p1=(0,0),p2=(100,0)); dim.render()
    doc.header['$LUNITS'] = 2
    stream = io.StringIO(); doc.write(stream)
    return stream.getvalue().encode('utf-8'), [e.dxf.handle for e in (line,circle,arc,poly,poly2,text,spline,insert)]

class APITest(unittest.TestCase):
    def setUp(self):
        DOCS.clear()
        self.client = TestClient(app)
        self.raw, self.ids = fixture()
        response = self.client.post('/api/open',files={'file':('한글.dxf',self.raw)})
        self.assertEqual(response.status_code,200,response.text)
        self.data = response.json()
        self.query = '?document_id='+self.data['document_id']

    def edit(self, **kw):
        return self.client.post('/api/edit'+self.query,json=kw)

    def export(self):
        r = self.client.get('/api/export/dxf'+self.query)
        self.assertEqual(r.status_code,200,r.text)
        return ezdxf.read(io.StringIO(r.content.decode('utf-8')))

    def test_open_units_layers_text_and_curves(self):
        self.assertEqual(self.data['units'],4)
        layers = {l['name']:l for l in self.data['layers']}
        self.assertFalse(layers['off']['visible'])
        self.assertTrue(layers['locked']['locked'])
        entities = {e['id']:e for e in self.data['entities']}
        self.assertEqual(entities[self.ids[3]]['segments'][0]['type'],'ARC')
        self.assertEqual(entities[self.ids[5]]['text'],'테스트')
        self.assertEqual(entities[self.ids[4]]['type'],'POLYLINE')
        self.assertTrue(entities[self.ids[6]]['pts'])
        self.assertTrue(entities[self.ids[6]]['approximate'])
        self.assertNotIn('DIMENSION',self.data['unsupported'])
        self.assertTrue(any(e['type']=='DIMENSION' and e['segments'] for e in self.data['entities']))
        self.assertTrue(any(e['type']=='INSERT' and e['segments'] for e in self.data['entities']))
        self.assertNotIn('LINE',self.data['unsupported'])
        self.assertTrue(any(e.get('projected') and e.get('display_only') for e in self.data['entities']))

    def test_move_undo_redo_preserves_full_document(self):
        r = self.edit(op='move',handles=self.ids[:2],dx=7,dy=-3)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.export().entitydb[self.ids[0]].dxf.start,(7,-3,0))
        self.assertEqual(self.client.post('/api/history/undo'+self.query).status_code,200)
        self.assertEqual(self.export().entitydb[self.ids[0]].dxf.start,(0,0,0))
        self.client.post('/api/history/redo'+self.query)
        doc = self.export()
        self.assertEqual(doc.entitydb[self.ids[1]].dxf.center,(57,37,0))
        self.assertEqual(doc.entitydb[self.ids[6]].dxftype(),'SPLINE')
        self.assertEqual(doc.entitydb[self.ids[7]].dxf.name,'fixture')
        self.assertEqual(len(doc.modelspace().query('DIMENSION')),1)
        self.assertEqual(len(doc.blocks['fixture']),1)
        self.assertEqual(doc.header['$LUNITS'],2)
        self.assertFalse(doc.audit().has_errors)

    def test_delete_undo_and_redo_branch(self):
        self.assertEqual(self.edit(op='delete',handles=self.ids[:2]).status_code,200)
        self.assertEqual(len(self.export().modelspace()),self.data['total']-2)
        self.client.post('/api/history/undo'+self.query)
        self.assertEqual(len(self.export().modelspace()),self.data['total'])
        self.edit(op='move',handle=self.ids[0],dx=1)
        self.assertEqual(self.client.post('/api/history/redo'+self.query).status_code,400)

    def test_atomic_batch_no_partial_changes(self):
        r = self.edit(op='move',handles=[self.ids[0],'DEADBEEF'],dx=3)
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.export().entitydb[self.ids[0]].dxf.start,(0,0,0))
        self.assertEqual(self.client.post('/api/history/undo'+self.query).status_code,400)

    def test_add_copy_properties(self):
        self.assertEqual(self.edit(op='add_line',x1=1,y1=2,x2=3,y2=4).status_code,200)
        self.assertEqual(self.edit(op='add_circle',x1=9,y1=10,radius=2).status_code,200)
        self.assertEqual(self.edit(op='copy',handle=self.ids[0],dx=1,dy=2).status_code,200)
        self.assertEqual(len(self.export().modelspace()),self.data['total']+3)
        self.edit(op='set_line',handle=self.ids[0],x1=0,y1=0,x2=30,y2=40)
        self.assertEqual(self.export().entitydb[self.ids[0]].dxf.end,(30,40,0))
        self.edit(op='set_circle',handle=self.ids[1],x1=4,y1=5,radius=8)
        self.assertEqual(self.export().entitydb[self.ids[1]].dxf.radius,8)

    def test_validation_and_locked_layers(self):
        for body in [dict(op='add_circle',radius=-1),dict(op='bogus'),dict(op='move',dx='NaN')]:
            self.assertEqual(self.edit(**body).status_code,422)
        self.assertEqual(self.edit(op='add_line').status_code,400)
        locked = next(e.dxf.handle for e in DOCS[self.data['document_id']].doc.modelspace() if e.dxf.layer=='locked')
        self.assertEqual(self.edit(op='delete',handle=locked).status_code,400)
        self.assertEqual(self.edit(op='delete',handle=self.ids[6]).status_code,400)
        self.assertEqual(self.edit(op='move',handle=self.ids[0],revision=99).status_code,409)

    def test_sessions_are_isolated(self):
        other = TestClient(app)
        self.assertEqual(other.post('/api/edit',json=dict(op='delete',handle=self.ids[0])).status_code,404)
        d = other.post('/api/open',files={'file':('other.dxf',self.raw)}).json()
        self.edit(op='delete',handle=self.ids[0])
        r = other.get('/api/export/dxf?document_id='+d['document_id'])
        self.assertEqual(len(ezdxf.read(io.StringIO(r.content.decode())).modelspace()),self.data['total'])
        self.assertEqual(other.get('/api/export/dxf?document_id=missing').status_code,404)

    def test_bad_files_and_size_limit(self):
        for name,data in [('bad.exe',b'x'),('bad.dxf',b'not dxf')]:
            self.assertIn(self.client.post('/api/open',files={'file':(name,data)}).status_code,(400,422))
        r = self.client.post('/api/open',files={'file':('big.dxf',b'0'*(40*1024*1024+1))})
        self.assertEqual(r.status_code,413)

    def test_oda_missing_and_converter_errors(self):
        with patch('server.odafc.is_installed',return_value=False):
            self.assertFalse(self.client.get('/api/status').json()['oda_installed'])
            self.assertEqual(self.client.post('/api/open',files={'file':('x.dwg',b'AC1032')}).status_code,422)
            self.assertEqual(self.client.get('/api/export/dwg'+self.query).status_code,422)
        with patch('server.odafc.is_installed',return_value=True),patch('server.odafc.readfile',side_effect=RuntimeError('bad conversion')):
            self.assertEqual(self.client.post('/api/open',files={'file':('x.dwg',b'AC1032')}).status_code,422)

    def test_close_and_session_limit(self):
        for _ in range(7):
            self.assertEqual(self.client.post('/api/open',files={'file':('x.dxf',self.raw)}).status_code,200)
        self.assertEqual(self.client.post('/api/open',files={'file':('x.dxf',self.raw)}).status_code,503)
        self.assertEqual(self.client.delete('/api/document'+self.query).status_code,200)
        self.assertEqual(self.client.get('/api/export/dxf'+self.query).status_code,404)

    def test_history_limit(self):
        for _ in range(32):
            self.assertEqual(self.edit(op='move',handle=self.ids[0],dx=1).status_code,200)
        s = DOCS[self.data['document_id']]
        self.assertEqual(len(s.undo),30)

    def test_original_bytes_unchanged(self):
        before = bytes(self.raw)
        self.edit(op='delete',handle=self.ids[0])
        self.export()
        self.assertEqual(self.raw,before)
        r = self.client.get('/api/export/dxf'+self.query)
        self.assertIn('edited',r.headers['content-disposition'])

if __name__ == '__main__':
    unittest.main()
