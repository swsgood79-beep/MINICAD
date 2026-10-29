"""Read-only DWG fallback: build supported display entities from the public database API.

This path does not write a DXF/DWG file. Unsupported data is counted, never silently
presented as a complete original document, and export remains blocked.
"""
import math
from collections import Counter
import ezdxf
from cad_core import Drawing, CADProblem


def import_database(data, filename):
    doc=ezdxf.new('R2018')
    units=data.get('header',{}).get('INSUNITS',0)
    doc.units=units if isinstance(units,int) and 0<=units<=24 else 0
    omitted=Counter()
    root_omitted=0
    count=0
    def number(value):
        if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1e11:
            raise ValueError('invalid coordinate')
        return float(value)
    def point(value):
        if not isinstance(value,dict):raise ValueError('missing point')
        return (number(value.get('x')),number(value.get('y')),number(value.get('z',0)))
    def angle(value):return math.degrees(number(value))
    def ensure_layer(name):
        if not isinstance(name,str):raise ValueError('invalid layer')
        if name not in doc.layers:doc.layers.new(name)
        return name
    tables=data.get('tables',{})
    for layer in tables.get('LAYER',{}).get('entries',[]):
        try:
            name=ensure_layer(layer['name'])
            target=doc.layers.get(name)
            if layer.get('off'):target.off()
            if layer.get('frozen'):target.freeze()
            if layer.get('locked'):target.lock()
        except (ValueError,KeyError,ezdxf.DXFError):omitted['LAYER']+=1
    blocks=tables.get('BLOCK_RECORD',{}).get('entries',[])
    for block in blocks:
        try:
            name=block['name']
            if not isinstance(name,str) or name.upper().startswith(('*MODEL_SPACE','*PAPER_SPACE')):continue
            if name not in doc.blocks:
                doc.blocks.new(name,base_point=point(block.get('basePoint',{'x':0,'y':0,'z':0})))
        except (ValueError,KeyError,ezdxf.DXFError):omitted['BLOCK']+=1
    def add(layout,e):
        nonlocal count
        count+=1
        if count>120000:raise CADProblem(413,'DWG 대체 읽기의 객체 한도(120,000개)를 초과했습니다.')
        kind=e.get('type','UNKNOWN')
        if e.get('isInPaperSpace'):return True
        try:
            attrs={'layer':ensure_layer(e.get('layer','0'))}
            if 'extrusionDirection' in e and e['extrusionDirection'] is not None:
                attrs['extrusion']=point(e['extrusionDirection'])
            if e.get('isVisible') is False:attrs['invisible']=1
            if kind=='LINE':layout.add_line(point(e['startPoint']),point(e['endPoint']),dxfattribs=attrs)
            elif kind in ('CIRCLE','ARC'):
                radius=number(e['radius'])
                if radius<=0:raise ValueError('invalid radius')
                if kind=='CIRCLE':layout.add_circle(point(e['center']),radius,dxfattribs=attrs)
                else:layout.add_arc(point(e['center']),radius,angle(e['startAngle']),angle(e['endAngle']),dxfattribs=attrs)
            elif kind=='POINT':layout.add_point(point(e['position']),dxfattribs=attrs)
            elif kind in ('LWPOLYLINE','POLYLINE2D'):
                pts=[(number(v['x']),number(v['y']),number(v.get('bulge',0))) for v in e['vertices']]
                attrs['elevation']=number(e.get('elevation',0))
                # 2D polylines are equivalent for the screen-only normalized document.
                layout.add_lwpolyline(pts,format='xyb',close=bool(e.get('flag',0)&(512 if kind=='LWPOLYLINE' else 1)),dxfattribs=attrs)
            elif kind in ('TEXT','ATTRIB','ATTDEF'):
                attrs.update(insert=point(e['startPoint']),height=number(e.get('textHeight',1)),rotation=angle(e.get('rotation',0)))
                layout.add_text(str(e.get('text','')),dxfattribs=attrs)
            elif kind=='MTEXT':
                attrs.update(insert=point(e['insertionPoint']),char_height=number(e.get('textHeight',1)),rotation=angle(e.get('rotation',0)))
                layout.add_mtext(str(e.get('text','')),dxfattribs=attrs)
            elif kind in ('INSERT','DIMENSION'):
                name=e.get('name','')
                if name not in doc.blocks:raise ValueError('missing block')
                if kind=='DIMENSION':
                    # Preserve the existing dimension picture; do not invent a new measured label.
                    layout.new_entity('DIMENSION',dxfattribs={**attrs,'geometry':name,'defpoint':point(e.get('definitionPoint',{'x':0,'y':0})), 'dimtype':int(e.get('dimensionType',0))})
                else:
                    if e.get('rowCount',1)>1 or e.get('columnCount',1)>1:
                        raise ValueError('array insert requires unsupported layout')
                    attrs.update(xscale=number(e.get('xScale',1)),yscale=number(e.get('yScale',1)),zscale=number(e.get('zScale',1)),rotation=angle(e.get('rotation',0)))
                    layout.add_blockref(name,point(e['insertionPoint']),dxfattribs=attrs)
            else:raise ValueError('unsupported entity')
            return True
        except (ValueError,TypeError,KeyError,ezdxf.DXFError):
            omitted[kind]+=1
            return False
    for block in blocks:
        name=block.get('name','')
        if name.upper().startswith(('*MODEL_SPACE','*PAPER_SPACE')):continue
        if name in doc.blocks:
            for e in block.get('entities',[]):add(doc.blocks[name],e)
    for e in data.get('entities',[]):
        if not add(doc.modelspace(),e):root_omitted+=1
    if not len(doc.modelspace()):raise CADProblem(422,'DWG에서 표시 가능한 기본 객체를 찾지 못했습니다.')
    warnings=['DWG 대체 읽기: 내부 파일 변환을 우회한 부분 표시입니다. 객체·폰트·치수 배치가 원본과 다를 수 있습니다. 화면 수정·측정·인쇄만 지원하며 파일 저장은 하지 않습니다.']
    decoder_errors=data.get('decoderErrors',0)
    unknown=data.get('unknownEntityCount',0)
    if decoder_errors:warnings.append(f'DWG 해석기 경고 코드: {decoder_errors}. 원본 CAD와 비교하세요.')
    if unknown:warnings.append(f'해석기가 인식하지 못한 객체 {unknown}개가 있습니다.')
    if omitted:warnings.append('대체 읽기에서 표시하지 못한 항목: '+', '.join(f'{k} {v}' for k,v in sorted(omitted.items())))
    result=Drawing(doc,filename,warnings=warnings,source_format='dwg')
    result.import_unsupported=dict(omitted)
    result.unrendered_roots=root_omitted
    return result
