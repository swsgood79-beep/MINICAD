import copy
import json
import math
from pathlib import Path
import unittest
import ezdxf
from cad_core import Drawing,serialize,CADProblem,edit_document
from browser_runtime import payload
from dwg_database import import_database

class DatabaseFallbackTest(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).parent/'fixtures/sample_database.json').read_text())
    def test_actual_database_coordinates_units_and_closed_polyline(self):
        s=import_database(self.data,'actual.dwg')
        result=serialize(s)
        self.assertEqual(result['total'],6)
        self.assertEqual(result['units'],4)
        self.assertEqual(result['source_format'],'dwg')
        line=next(e for e in s.doc.modelspace().query('LINE') if abs(e.dxf.end.y-e.dxf.start.y)<1e-8)
        self.assertAlmostEqual((line.dxf.end-line.dxf.start).magnitude,100)
        self.assertEqual(s.doc.modelspace().query('CIRCLE')[0].dxf.radius,20)
        self.assertTrue(s.doc.modelspace().query('LWPOLYLINE')[0].closed)
        self.assertEqual(result['unsupported'],{})
        self.assertTrue(all(not l['locked'] for l in result['layers']))
    def test_omitted_objects_are_counted_and_reported(self):
        self.data['entities'].append({'type':'HATCH','layer':'0'})
        self.data['unknownEntityCount']=2
        result=serialize(import_database(self.data,'partial.dwg'))
        self.assertEqual(result['total'],7)
        self.assertEqual(result['unsupported']['HATCH'],1)
        self.assertFalse(any('DXF 문서에 유지' in w for w in result['warnings']))
        self.assertTrue(any('2개' in w for w in result['warnings']))
    def test_invalid_coordinates_not_changed_to_zero(self):
        self.data['tables']['LAYER']['entries'].append({'name':None,'off':True})
        self.data['entities'].append({'type':'LINE','startPoint':{'x':float('nan'),'y':0},'endPoint':{'x':1,'y':2}})
        self.data['entities'].append({'type':'ARC','center':{'x':0,'y':0},'radius':10,'startAngle':None,'endAngle':1})
        result=serialize(import_database(self.data,'bad-coordinate.dwg'))
        self.assertEqual(result['unsupported']['LINE'],1)
        self.assertEqual(result['unsupported']['ARC'],1)
        self.assertEqual(result['unsupported']['LAYER'],1)
        self.assertEqual(len(result['entities']),6)
    def test_block_rotation_and_layer_lock_are_preserved(self):
        self.data['tables']['LAYER']['entries'].append({'name':'locked','locked':True,'off':True})
        self.data['tables']['BLOCK_RECORD']['entries'].append({'name':'rotated','basePoint':{'x':0,'y':0},'entities':[{'type':'LINE','startPoint':{'x':0,'y':0},'endPoint':{'x':10,'y':0}}]})
        self.data['entities'].append({'type':'INSERT','name':'rotated','insertionPoint':{'x':100,'y':200},'xScale':1,'yScale':1,'zScale':1,'rotation':math.pi/2,'layer':'locked'})
        result=serialize(import_database(self.data,'block.dwg'))
        block=next(e for e in result['entities'] if e['type']=='INSERT')
        a,b=block['segments'][0]['a'],block['segments'][0]['b']
        self.assertAlmostEqual(a[0],100);self.assertAlmostEqual(a[1],200)
        self.assertAlmostEqual(b[0],100);self.assertAlmostEqual(b[1],210)
        layer=next(l for l in result['layers'] if l['name']=='locked')
        self.assertTrue(layer['locked']);self.assertFalse(layer['visible'])
    def test_unused_120001_entity_block_does_not_prevent_opening(self):
        line={'type':'LINE','startPoint':{'x':0,'y':0},'endPoint':{'x':100,'y':0}}
        self.data['entities']=[line]
        self.data['tables']['BLOCK_RECORD']['entries'].append({'name':'unused','entities':[line]*120001})
        s=import_database(self.data,'unused-block.dwg',entity_limit=8)
        self.assertEqual(len(s.doc.modelspace()),1)
        self.assertNotIn('unused',s.doc.blocks)
        self.assertFalse(serialize(s)['preview'])

    def test_excess_model_objects_open_with_explicit_preview(self):
        line={'type':'LINE','startPoint':{'x':0,'y':0},'endPoint':{'x':100,'y':0}}
        self.data['entities']=[line]*11
        s=import_database(self.data,'large.dwg',entity_limit=4)
        result=serialize(s)
        self.assertTrue(result['preview'])
        self.assertEqual(result['total'],11)
        self.assertEqual(len(result['entities']),4)
        self.assertEqual(result['history_limit'],3)
        self.assertTrue(any('전체 도면' in w for w in result['warnings']))
        for _ in range(5):edit_document(s,payload({'op':'move','handle':result['entities'][0]['id'],'dx':1}))
        self.assertEqual(len(s.undo),3)
        with self.assertRaisesRegex(CADProblem,'추가'):
            edit_document(s,payload({'op':'add_line','x2':10}))

    def test_referenced_blocks_load_depth_first_within_budget(self):
        line={'type':'LINE','startPoint':{'x':0,'y':0},'endPoint':{'x':100,'y':0}}
        insert=lambda name:{'type':'INSERT','name':name,'insertionPoint':{'x':0,'y':0}}
        self.data['entities']=[insert('OUTER')]
        self.data['tables']['BLOCK_RECORD']['entries']=[{'name':'outer','entities':[insert('inner')]*10},{'name':'inner','entities':[line]*50}]
        result=serialize(import_database(self.data,'nested.dwg',entity_limit=6))
        self.assertTrue(result['preview'])
        self.assertEqual(len(result['entities']),1)
        segments=result['entities'][0]['segments'][0]['segments']
        self.assertTrue(segments)
        self.assertEqual(segments[0]['type'],'LINE')
        self.assertEqual(segments[0]['b'],[100,0])

    def test_unsupported_metadata_does_not_hide_later_supported_geometry(self):
        line={'type':'LINE','startPoint':{'x':0,'y':0},'endPoint':{'x':100,'y':0}}
        self.data['entities']=[{'type':'HATCH'}]*12+[line]
        result=serialize(import_database(self.data,'unsupported-first.dwg',entity_limit=1))
        self.assertEqual(result['entities'][0]['b'],[100,0])
        self.assertEqual(result['unsupported']['HATCH'],12)
        self.assertEqual(result['total'],13)

    def test_visible_layers_receive_preview_budget_first(self):
        self.data['tables']['LAYER']['entries'].append({'name':'hidden','off':True})
        line={'type':'LINE','startPoint':{'x':0,'y':0},'endPoint':{'x':100,'y':0}}
        self.data['entities']=[dict(line,layer='hidden')]*10+[dict(line,layer='0')]
        result=serialize(import_database(self.data,'layers.dwg',entity_limit=1))
        self.assertEqual(result['entities'][0]['layer'],'0')
        self.assertTrue(result['preview'])

    def test_expanded_geometry_is_bounded_and_partial_polyline_not_editable(self):
        doc=ezdxf.new()
        poly=doc.modelspace().add_lwpolyline([(i,0) for i in range(20)])
        s=Drawing(doc,'poly.dxf',display_limit=4)
        result=serialize(s)
        self.assertTrue(result['preview'])
        self.assertTrue(result['entities'][0]['partial'])
        self.assertEqual(len(result['entities'][0]['segments']),3)
        with self.assertRaisesRegex(CADProblem,'일부만 표시'):
            edit_document(s,payload({'op':'move','handle':poly.dxf.handle,'dx':1}))

    def test_repeated_block_instances_share_a_global_render_budget(self):
        doc=ezdxf.new();b=doc.blocks.new('shared')
        for i in range(20):b.add_line((i,0),(i,1))
        for i in range(20):doc.modelspace().add_blockref('shared',(i*100,0))
        result=serialize(Drawing(doc,'expanded.dxf',display_limit=12))
        self.assertTrue(result['preview'])
        self.assertEqual(len(result['entities']),1)
        self.assertEqual(len(result['entities'][0]['segments']),11)
        self.assertTrue(result['entities'][0]['partial'])

    def test_no_display_entities_is_a_failure(self):
        self.data['entities']=[{'type':'UNSUPPORTED'}]
        with self.assertRaises(CADProblem):import_database(self.data,'unsupported.dwg')

if __name__=='__main__':unittest.main()
