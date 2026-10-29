"""Read-only DWG fallback: build supported display entities from the public database API.

This path does not write a DXF/DWG file. Unsupported data is counted, never silently
presented as a complete original document, and export remains blocked.
"""
import math
from collections import deque
from collections import Counter
import ezdxf
from cad_core import Drawing, CADProblem


def import_database(data, filename, entity_limit=120000):
    doc=ezdxf.new('R2018')
    units=data.get('header',{}).get('INSUNITS',0)
    doc.units=units if isinstance(units,int) and 0<=units<=24 else 0
    omitted=Counter()
    root_omitted=0
    count=0
    limited_roots=0
    limited_block_entities=0
    pending=deque()
    scheduled=set()
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
    blocks={b['name']:b for b in tables.get('BLOCK_RECORD',{}).get('entries',[])
            if isinstance(b.get('name'),str) and not b['name'].upper().startswith(('*MODEL_SPACE','*PAPER_SPACE'))}
    block_names={name.casefold():name for name in blocks}
    roots=[e for e in data.get('entities',[]) if not e.get('isInPaperSpace')]
    hidden={l['name'].casefold() for l in tables.get('LAYER',{}).get('entries',[]) if isinstance(l.get('name'),str) and (l.get('off') or l.get('frozen'))}
    roots.sort(key=lambda e:e.get('isVisible') is False or str(e.get('layer') or '0').casefold() in hidden)
    def references(entities):
        return (block_names[e['name'].casefold()] for e in entities if e.get('type') in ('INSERT','DIMENSION') and isinstance(e.get('name'),str) and e['name'].casefold() in block_names)
    # Inspect references cheaply; unused definitions never become ezdxf objects or consume the budget.
    reachable=set()
    work=list(references(roots))
    while work:
        name=work.pop()
        if name in reachable:continue
        reachable.add(name)
        work.extend(n for n in references(blocks[name].get('entities',[])) if n not in reachable)
    supported={'LINE','CIRCLE','ARC','POINT','LWPOLYLINE','POLYLINE2D','TEXT','ATTRIB','ATTDEF','MTEXT','INSERT','DIMENSION'}
    candidate_count=sum(e.get('type') in supported for e in roots)+sum(sum(e.get('type') in supported for e in blocks[n].get('entities',[])) for n in reachable)
    # If a preview is needed, reserve space for the geometry behind the selected inserts.
    root_limit=min(len(roots),max(1,entity_limit//2)) if candidate_count>entity_limit and reachable else entity_limit
    def ensure_block(name):
        name=block_names.get(name.casefold()) if isinstance(name,str) else None
        if name not in blocks:raise ValueError('missing block')
        if name not in scheduled:
            block=blocks[name]
            doc.blocks.new(name,base_point=point(block.get('basePoint',{'x':0,'y':0,'z':0})))
            scheduled.add(name)
            pending.append(name)
        return name
    def add(layout,e):
        nonlocal count
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
                name=ensure_block(e.get('name',''))
                if kind=='DIMENSION':
                    # Preserve the existing dimension picture; do not invent a new measured label.
                    layout.new_entity('DIMENSION',dxfattribs={**attrs,'geometry':name,'defpoint':point(e.get('definitionPoint',{'x':0,'y':0})), 'dimtype':int(e.get('dimensionType',0))})
                else:
                    if e.get('rowCount',1)>1 or e.get('columnCount',1)>1:
                        raise ValueError('array insert requires unsupported layout')
                    attrs.update(xscale=number(e.get('xScale',1)),yscale=number(e.get('yScale',1)),zscale=number(e.get('zScale',1)),rotation=angle(e.get('rotation',0)))
                    layout.add_blockref(name,point(e['insertionPoint']),dxfattribs=attrs)
            else:raise ValueError('unsupported entity')
            count+=1
            return True
        except (ValueError,TypeError,KeyError,ezdxf.DXFError):
            omitted[kind]+=1
            return False
    for index,e in enumerate(roots):
        if len(doc.modelspace())>=root_limit or count>=entity_limit:
            limited_roots=len(roots)-index
            root_omitted+=limited_roots
            break
        if not add(doc.modelspace(),e):root_omitted+=1
    loaded=set()
    def load_block(name,active=()):
        nonlocal limited_block_entities
        if name in loaded or name in active:return
        entries=blocks[name].get('entities',[])
        if len(active)>=8:
            limited_block_entities+=len(entries)
            loaded.add(name)
            return
        for index,e in enumerate(entries):
            if count>=entity_limit:
                limited_block_entities+=len(entries)-index
                break
            add(doc.blocks[name],e)
            # Descend immediately, so the budget cannot be spent on empty insertion shells.
            for child in references([e]):
                if child in scheduled:load_block(child,active+(name,))
        loaded.add(name)
    while pending:
        load_block(pending.popleft())
    if not len(doc.modelspace()):raise CADProblem(422,'DWG에서 표시 가능한 기본 객체를 찾지 못했습니다.')
    warnings=['DWG 대체 읽기: 내부 파일 변환을 우회한 부분 표시입니다. 객체·폰트·치수 배치가 원본과 다를 수 있습니다. 화면 수정·측정·인쇄만 지원하며 파일 저장은 하지 않습니다.']
    decoder_errors=data.get('decoderErrors',0)
    unknown=data.get('unknownEntityCount',0)
    if decoder_errors:warnings.append(f'DWG 해석기 경고 코드: {decoder_errors}. 원본 CAD와 비교하세요.')
    if unknown:warnings.append(f'해석기가 인식하지 못한 객체 {unknown}개가 있습니다.')
    if omitted:warnings.append('대체 읽기에서 표시하지 못한 항목: '+', '.join(f'{k} {v}' for k,v in sorted(omitted.items())))
    result=Drawing(doc,filename,warnings=warnings,source_format='dwg')
    result.preview=bool(limited_roots or limited_block_entities)
    result.display_limit=min(30000,entity_limit)
    result.history_limit=3 if candidate_count>30000 or result.preview else 30
    if result.preview:
        result.warnings.insert(0,f'큰 도면 부분 미리보기: 처리 한도 안의 객체를 먼저 열었습니다. 모델 공간 {len(roots):,}개 중 {len(doc.modelspace()):,}개를 불러왔고, 모델 공간 {limited_roots:,}개와 블록 내부 {limited_block_entities:,}개는 추가로 생략했습니다. 전체 도면이 아니므로 누락된 부분의 측정·전체 인쇄에 사용하지 마세요.')
    result.import_unsupported=dict(omitted)
    result.unrendered_roots=root_omitted
    return result
