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

    def test_cloned_dimension_picture_keeps_nested_translation(self):
        # Anonymous picture coordinates are absolute; clone_ins_pt restores the
        # local block position before its parent insertion is applied.
        self.data['entities']=[{'type':'INSERT','name':'assembly','insertionPoint':{'x':100,'y':200}}]
        self.data['tables']['BLOCK_RECORD']['entries']=[
            {'name':'assembly','entities':[{'type':'DIMENSION','dimensionType':3,'name':'*D1',
                'definitionPoint':{'x':0,'y':0},'insertionPoint':{'x':-1000,'y':-2000}}]},
            {'name':'*D1','entities':[{'type':'LINE','startPoint':{'x':1010,'y':2020},'endPoint':{'x':1040,'y':2020}}]},
        ]
        result=serialize(import_database(self.data,'cloned.dwg'))
        line=result['entities'][0]['segments'][0]['segments'][0]
        self.assertEqual(line['a'],[110,220]);self.assertEqual(line['b'],[140,220])
        self.assertNotIn('DIMENSION',result['unsupported'])

    def test_mirrored_circle_and_arc_use_world_coordinates(self):
        from cad_core import primitive
        doc=ezdxf.new();m=doc.modelspace()
        circle=m.add_circle((-10,20),5,dxfattribs={'extrusion':(0,0,-1)})
        result=primitive(circle)
        self.assertEqual(result['c'],[10,20])
        s=Drawing(doc,'mirror.dxf')
        edit_document(s,payload({'op':'set_circle','handle':circle.dxf.handle,'x1':15,'y1':25,'radius':7}))
        self.assertEqual(serialize(s)['entities'][0]['c'],[15,25])
        arc=m.add_arc((-10,20),5,0,90,dxfattribs={'extrusion':(0,0,-1)})
        result=primitive(arc)
        self.assertEqual(result['c'],[10,20])
        self.assertAlmostEqual(result['start'],90);self.assertAlmostEqual(result['end'],180)
        block=doc.blocks.new('mirrored');block.add_circle((5,0),2)
        insert=m.add_blockref('mirrored',(100,0),dxfattribs={'extrusion':(0,0,-1)})
        self.assertEqual(primitive(insert)['segments'][0]['c'],[-105,0])

    def test_curves_solids_and_attribute_text_display_without_becoming_editable(self):
        self.data['entities']=[
            {'type':'ELLIPSE','center':{'x':0,'y':0},'majorAxisEndPoint':{'x':10,'y':0},'axisRatio':0.5},
            {'type':'SPLINE','degree':2,'controlPoints':[{'x':0,'y':0},{'x':5,'y':10},{'x':10,'y':0}],'knots':[0,0,0,1,1,1]},
            {'type':'SOLID','corner1':{'x':0,'y':0},'corner2':{'x':1,'y':0},'corner3':{'x':0,'y':1}},
            {'type':'ATTRIB','text':{'text':'part A','startPoint':{'x':0,'y':0},'textHeight':2}},
        ]
        s=import_database(self.data,'curves.dwg');result=serialize(s)
        self.assertEqual(result['unsupported'],{})
        self.assertEqual(len(result['entities']),4)
        for curve in result['entities'][:2]:
            self.assertTrue(curve['approximate']);self.assertGreater(len(curve['pts']),8)
            with self.assertRaises(CADProblem):edit_document(s,payload({'op':'move','handle':curve['id'],'dx':1}))
        self.assertTrue(result['entities'][2]['filled'])
        self.assertEqual(result['entities'][3]['text'],'part A')

    def test_projected_3d_line_is_displayed_but_cannot_be_edited(self):
        doc=ezdxf.new();line=doc.modelspace().add_line((0,0,0),(3,4,12));s=Drawing(doc,'3d.dxf')
        result=serialize(s)
        self.assertTrue(result['entities'][0]['projected'])
        self.assertEqual(result['entities'][0]['b'],[3,4])
        self.assertTrue(any('XY' in w for w in result['warnings']))
        with self.assertRaises(CADProblem):edit_document(s,payload({'op':'move','handle':line.dxf.handle,'dx':1}))

    def test_no_display_entities_is_a_failure(self):
        self.data['entities']=[{'type':'UNSUPPORTED'}]
        with self.assertRaises(CADProblem):import_database(self.data,'unsupported.dwg')

    def test_cached_dwg_pictures_respect_budget_edits_and_history(self):
        s=import_database(self.data,'cache.dwg')
        initial=serialize(s)
        s.display_limit=2
        self.assertTrue(serialize(s)['preview'])
        s.display_limit=2000000
        self.assertEqual(serialize(s)['entities'],initial['entities'])
        line=next(e for e in initial['entities'] if e['type']=='LINE')
        edited=edit_document(s,payload({'op':'move','handle':line['id'],'dx':7,'dy':-3}))
        fresh=serialize(Drawing(copy.deepcopy(s.doc),'fresh.dwg',source_format='dwg'))
        self.assertEqual(edited['entities'],fresh['entities'])
        moved=next(e for e in edited['entities'] if e['id']==line['id'])
        self.assertEqual(moved['a'],[line['a'][0]+7,line['a'][1]-3])
        s.doc=s.undo.pop()
        self.assertEqual(serialize(s)['entities'],initial['entities'])

if __name__=='__main__':unittest.main()
