import copy
import json
import math
from pathlib import Path
import unittest
import ezdxf
from cad_core import serialize,CADProblem
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
        self.data['entities'].append({'type':'LINE','startPoint':{'x':float('nan'),'y':0},'endPoint':{'x':1,'y':2}})
        self.data['entities'].append({'type':'ARC','center':{'x':0,'y':0},'radius':10,'startAngle':None,'endAngle':1})
        result=serialize(import_database(self.data,'bad-coordinate.dwg'))
        self.assertEqual(result['unsupported']['LINE'],1)
        self.assertEqual(result['unsupported']['ARC'],1)
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
    def test_no_display_entities_is_a_failure(self):
        self.data['entities']=[{'type':'UNSUPPORTED'}]
        with self.assertRaises(CADProblem):import_database(self.data,'unsupported.dwg')

if __name__=='__main__':unittest.main()
