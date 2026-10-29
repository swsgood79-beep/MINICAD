"""Optimized block pictures must match ezdxf's general virtual-entity path."""
import math
import unittest
from unittest.mock import patch
import ezdxf
from cad_core import Drawing,primitive,serialize

class BlockDisplayTest(unittest.TestCase):
    def fixture(self):
        doc=ezdxf.new('R2018');m=doc.modelspace()
        leaf=doc.blocks.new('leaf',base_point=(3,4,0))
        leaf.add_line((0,0),(20,30),dxfattribs={'color':1})
        leaf.add_circle((5,5),4)
        leaf.add_arc((10,20),6,350,50)
        leaf.add_lwpolyline([(0,0,0.5),(20,0,0),(20,20,0)],format='xyb',close=True)
        leaf.add_text('Label',dxfattribs={'height':2,'insert':(10,20),'rotation':20})
        leaf.add_mtext('two\\P lines',dxfattribs={'char_height':2,'insert':(10,30)})
        dim=leaf.add_linear_dim(base=(0,40),p1=(0,0),p2=(20,0));dim.render()
        outer=doc.blocks.new('outer',base_point=(2,1,0))
        outer.add_blockref('leaf',(20,10),dxfattribs={'rotation':17})
        outer.add_line((0,0),(10,0))
        return doc,m

    def assert_picture(self,a,b):
        self.assertEqual(a.keys(),b.keys())
        for key,x in a.items():
            y=b[key]
            if key=='segments':
                self.assertEqual(len(x),len(y))
                for u,v in zip(x,y):self.assert_picture(u,v)
            elif key in ('a','b','c'):
                self.assertLess(math.dist(x,y),1e-8)
            elif key=='pts':
                self.assertEqual(len(x),len(y))
                for u,v in zip(x,y):self.assertLess(math.dist(u,v),1e-8)
            elif key in ('start','end','rotation'):
                self.assertLess(abs((x-y+180)%360-180),1e-8)
            elif type(x) is float:self.assertAlmostEqual(x,y,places=8)
            else:self.assertEqual(x,y)

    def test_nested_blocks_base_points_text_dimensions_and_rotations(self):
        doc,m=self.fixture()
        for scale in (1,2):
            for rotation in (0,35,270):
                e=m.add_blockref('outer',(100,200),dxfattribs={'rotation':rotation,'xscale':scale,'yscale':scale,'zscale':scale})
                fast=primitive(e)
                with patch('cad_core.block_picture',return_value=None):ref=primitive(e)
                self.assert_picture(fast,ref)

    def test_mirrored_text_and_nonuniform_geometry_keep_general_transform(self):
        doc,m=self.fixture()
        for attrs in ({'xscale':-1},{'extrusion':(0,0,-1)},{'xscale':2,'yscale':1}):
            e=m.add_blockref('outer',(50,70),dxfattribs=attrs)
            fast=primitive(e)
            with patch('cad_core.block_picture',return_value=None):ref=primitive(e)
            self.assert_picture(fast,ref)

    def test_rescaled_sampled_curves_keep_tolerance_and_path(self):
        doc=ezdxf.new();b=doc.blocks.new('curves');b.add_spline([(0,0),(10,20),(20,0)])
        b.add_ellipse((10,10),major_axis=(10,0),ratio=.5)
        for scale in (.1,10):
            e=doc.modelspace().add_blockref('curves',(100,200),dxfattribs={'xscale':scale,'yscale':scale})
            fast=primitive(e)
            with patch('cad_core.block_picture',return_value=None):ref=primitive(e)
            self.assert_picture(fast,ref)

    def test_cached_templates_preserve_global_budget_and_later_full_scene(self):
        doc,m=self.fixture()
        for i in range(5):m.add_blockref('outer',(i*100,0))
        whole=serialize(Drawing(doc,'full.dxf'))
        partial=serialize(Drawing(doc,'partial.dxf',display_limit=9))
        self.assertTrue(partial['preview']);self.assertTrue(partial['entities'][0]['partial'])
        self.assertEqual(serialize(Drawing(doc,'full-again.dxf'))['entities'],whole['entities'])

    def test_cycles_and_depth_limits_remain_bounded(self):
        doc=ezdxf.new();a=doc.blocks.new('a');b=doc.blocks.new('b')
        a.add_line((0,0),(10,0));a.add_blockref('b',(0,0));b.add_blockref('a',(0,0))
        e=doc.modelspace().add_blockref('a',(10,20))
        fast=primitive(e)
        with patch('cad_core.block_picture',return_value=None):ref=primitive(e)
        self.assert_picture(fast,ref)

    def test_cache_capacity_falls_back_without_cutting_drawing(self):
        doc,m=self.fixture()
        for i in range(4):m.add_blockref('outer',(i*100,0))
        with patch('cad_core.BLOCK_TEMPLATE_LIMIT',4),patch('cad_core.BLOCK_CACHE_LIMIT',8):
            fast=serialize(Drawing(doc,'bounded-cache.dxf'))
        with patch('cad_core.block_picture',return_value=None):
            ref=serialize(Drawing(doc,'reference.dxf'))
        self.assertFalse(fast['preview'])
        for a,b in zip(fast['entities'],ref['entities']):self.assert_picture(a,b)

    def count_wire(self,items,definitions):
        return sum(self.count_wire(definitions[item['$block']],definitions) if '$block' in item
                   else 1+self.count_wire(item.get('segments',[]),definitions) for item in items)

    def test_compact_nested_references_retain_full_display_and_share_definitions(self):
        doc,m=self.fixture()
        for i in range(8):m.add_blockref('outer',(i*100,20))
        s=Drawing(doc,'shared.dwg',source_format='dwg')
        full=serialize(s);wire=serialize(s,compact=True)
        self.assertFalse(wire['preview']);self.assertEqual(wire['unsupported'],full['unsupported'])
        self.assertEqual(wire['warnings'],full['warnings'])
        self.assertEqual(wire['total'],full['total'])
        self.assertEqual(len({e['segments'][0]['$block'] for e in wire['entities']}),1)
        self.assertEqual(self.count_wire(wire['entities'],wire['blockPictures']),self.count_wire(full['entities'],{}))
        self.assertLess(len(str(wire)),len(str(full)))
        self.assertFalse(doc.audit().has_errors)

    def test_compact_budget_after_full_cache_still_marks_partial_objects(self):
        doc,m=self.fixture();m.add_blockref('outer',(100,200));s=Drawing(doc,'budget.dwg',source_format='dwg')
        full=serialize(s,compact=True)
        s.display_limit=9;wire=serialize(s,compact=True);handles=set(s.display_partial_handles)
        ref=serialize(s)
        self.assertTrue(wire['preview']);self.assertEqual(wire['preview'],ref['preview'])
        self.assertEqual(handles,s.display_partial_handles)
        self.assertEqual(self.count_wire(wire['entities'],wire.get('blockPictures',{})),self.count_wire(ref['entities'],{}))
        s.display_limit=2000000
        self.assertEqual(serialize(s,compact=True),full)

    def test_compact_nested_unsupported_and_projection_warnings_match(self):
        doc=ezdxf.new();leaf=doc.blocks.new('leaf');outer=doc.blocks.new('outer')
        leaf.add_line((0,0,0),(3,4,12));leaf.add_hatch()
        outer.add_blockref('leaf',(10,20))
        for i in range(3):doc.modelspace().add_blockref('outer',(i*100,0))
        s=Drawing(doc,'warnings.dwg',source_format='dwg')
        full=serialize(s);wire=serialize(s,compact=True)
        self.assertEqual(wire['unsupported'],full['unsupported'])
        self.assertEqual(wire['warnings'],full['warnings'])
        self.assertEqual(self.count_wire(wire['entities'],wire.get('blockPictures',{})),self.count_wire(full['entities'],{}))

    def test_compact_edits_and_history_reuse_pristine_block_definitions(self):
        from cad_core import edit_document
        from browser_runtime import payload
        doc,m=self.fixture();m.add_blockref('outer',(100,200));line=m.add_line((0,0),(3,4))
        s=Drawing(doc,'edit.dwg',source_format='dwg');original=serialize(s,compact=True)
        edited=edit_document(s,payload({'op':'move','handle':line.dxf.handle,'dx':7,'dy':-3}),compact=True)
        self.assertEqual(edited['blockPictures'],original['blockPictures'])
        self.assertEqual(next(e for e in edited['entities'] if e['id']==line.dxf.handle)['a'],[7,-3])
        self.assertEqual(line.dxf.start,(0,0,0))
        s.doc=s.undo.pop()
        self.assertEqual(serialize(s,compact=True)['entities'],original['entities'])

    def test_compact_extreme_coordinates_use_existing_validation_path(self):
        doc=ezdxf.new();leaf=doc.blocks.new('leaf');leaf.add_line((1e11,0),(1e11,10))
        doc.modelspace().add_line((0,0),(3,4))
        doc.modelspace().add_blockref('leaf',(0,0),dxfattribs={'xscale':20,'yscale':20})
        s=Drawing(doc,'range.dwg',source_format='dwg')
        full=serialize(s);wire=serialize(s,compact=True)
        self.assertEqual(wire['unsupported'],full['unsupported'])
        self.assertEqual(wire['entities'],full['entities'])
        self.assertEqual(wire['warnings'],full['warnings'])

if __name__=='__main__':unittest.main()
