"""Shared ezdxf document engine for FastAPI and the browser Python worker."""
from copy import deepcopy
from dataclasses import dataclass, field
import math
from weakref import WeakKeyDictionary
import ezdxf
from ezdxf.path import make_path
from ezdxf.colors import aci2rgb

HISTORY = 30
BLOCK_TEMPLATE_LIMIT = 40000
BLOCK_CACHE_LIMIT = 200000
EDITABLE = {'LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'POINT'}
# DWG screen documents are immutable between committed edits/history switches.
# Keep display data outside the document so deepcopy never copies these trees.
# History documents share unchanged root pictures and disappear through weak keys.
_dwg_pictures = WeakKeyDictionary()
_block_pictures = WeakKeyDictionary()
_wire_pictures = WeakKeyDictionary()
_aci_colors={i:'#%02x%02x%02x'%tuple(aci2rgb(i)) for i in range(1,256)}

def xy(p):
    x,y=float(p[0]),float(p[1])
    if not (math.isfinite(x) and math.isfinite(y) and abs(x)<1e12 and abs(y)<1e12):
        raise ValueError('좌표 범위 초과')
    return [x,y]

def sampled(e,item):
    pts=[xy(p) for p in make_path(e).flattening(0.05,segments=8)]
    if not pts:raise ValueError('곡선 데이터 없음')
    item.update(pts=pts,display_only=True,approximate=True)

class DisplayLimit(ValueError):
    pass

class RenderBudget:
    def __init__(self,limit):self.remaining=limit;self.truncated=False
    def consume(self):
        if self.remaining<=0:
            self.truncated=True
            raise DisplayLimit('화면 표시 한도')
        self.remaining-=1

class PicturePool:
    """Wire-only block definitions; document and HTTP API representations stay intact."""
    def __init__(self):
        self.definitions={}
        self.references={}
        self.stats={}
        self.traits={}
        self.bounds={}
        self.summaries={}
        self.cache={'_cost':0}

    def summary(self,parts):
        identity=id(parts)
        if identity not in self.summaries:
            omitted={};projected=0;traits=[False,False,False];stored=0;bound=0.0
            def visit(item):
                nonlocal projected,stored,bound
                stored+=1
                if '$block' in item:
                    counts,n=self.stats[item['$block']]
                    projected+=n
                    for kind,count in counts.items():omitted[kind]=omitted.get(kind,0)+count
                    for i,flag in enumerate(self.traits[item['$block']]):traits[i]=traits[i] or flag
                    a,b,c,d,tx,ty=item['matrix']
                    bound=max(bound,max(abs(a)+abs(c),abs(b)+abs(d))*self.bounds[item['$block']]+max(abs(tx),abs(ty)))
                    return
                if item.get('projected'):projected+=1
                traits[0]=traits[0] or bool(item.get('approximate'))
                traits[1]=traits[1] or bool(item.get('projected'))
                traits[2]=traits[2] or item.get('text') is not None
                for kind,count in item.get('omitted',{}).items():omitted[kind]=omitted.get(kind,0)+count
                for key in ('a','b','c'):
                    if key in item:bound=max(bound,abs(item[key][0]),abs(item[key][1]))
                for point in item.get('pts',[]):bound=max(bound,abs(point[0]),abs(point[1]))
                for child in item.get('segments',[]):visit(child)
            for item in parts:visit(item)
            self.summaries[identity]=(omitted,projected,traits,stored,bound)
        return self.summaries[identity]

    def instance(self, parts, matrix):
        identity=id(parts)
        ref=self.references.get(identity)
        if ref is None:
            ref=str(len(self.definitions))
            self.references[identity]=ref
            self.definitions[ref]=parts
            omitted,projected,traits,_,bound=self.summary(parts)
            self.stats[ref]=(omitted,projected)
            self.traits[ref]=traits
            self.bounds[ref]=bound
        return [{'$block':ref,'matrix':matrix}]

    def reachable(self,entities):
        used=set()
        def visit(items):
            for item in items:
                if '$block' in item:
                    ref=item['$block']
                    if ref not in used:
                        used.add(ref);visit(self.definitions[ref])
                else:visit(item.get('segments',[]))
        visit(entities)
        return {ref:self.definitions[ref] for ref in used}

class CADProblem(ValueError):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)

@dataclass
class Drawing:
    doc: object
    name: str
    warnings: list[str] = field(default_factory=list)
    undo: list = field(default_factory=list)
    redo: list = field(default_factory=list)
    revision: int = 0
    source_format: str = 'dxf'
    import_unsupported: dict = field(default_factory=dict)
    unrendered_roots: int = 0
    preview: bool = False
    display_limit: int = 2000000
    history_limit: int = HISTORY
    display_partial_handles: set = field(default_factory=set)
    view_limited: bool = False

def planar(e):
    if e.dxftype() == 'POLYLINE' and not e.is_2d_polyline:
        return False
    normal = e.dxf.get('extrusion', (0, 0, 1))
    return abs(normal[0])<1e-10 and abs(normal[1])<1e-10 and abs(abs(normal[2])-1)<1e-10

def block_picture(e, depth, ancestors, budget, instances=None):
    """Reuse local 2D geometry; keep ezdxf's general transform for complex blocks.

    Only a planar similarity transform is eligible. Mirrored text and rescaled
    sampled curves use the established ezdxf transform path.
    The ezdxf document stays intact for editing/export.
    """
    if e.doc is None or not planar(e) or e.dxf.extrusion.x or e.dxf.extrusion.y:return None
    sx,sy=e.dxf.xscale,e.dxf.yscale
    if abs(sx)!=abs(sy) or not sx:return None
    name=e.dxf.name
    key=(name,depth,ancestors)
    cache=instances.cache if instances is not None else _block_pictures.setdefault(e.doc,{'_cost':0})
    if key not in cache:
        if len(cache)>=8192 or cache['_cost']>=BLOCK_CACHE_LIMIT:return None
        layout=e.block()
        kinds={'LINE','POINT','ARC','CIRCLE','LWPOLYLINE','POLYLINE','SOLID','TRACE','TEXT','MTEXT','INSERT','DIMENSION','SPLINE','ELLIPSE','LEADER'}
        if layout is None or any(child.dxftype() not in kinds for child in layout):
            cache[key]=None
        else:
            limit=min(budget.remaining if budget else BLOCK_TEMPLATE_LIMIT,
                      BLOCK_TEMPLATE_LIMIT,BLOCK_CACHE_LIMIT-cache['_cost'])
            local_budget=RenderBudget(limit)
            try:
                parts=[primitive(child,depth+1,ancestors+(name,),local_budget,instances) for child in layout]
                if local_budget.truncated:return None
                cost=limit-local_budget.remaining
                stored=instances.summary(parts)[3] if instances is not None else cost
                if stored>BLOCK_CACHE_LIMIT-cache['_cost'] or len(cache)>=8192:
                    if instances is not None:instances.summaries.pop(id(parts),None)
                    return None
                cache[key]=(parts,cost)
                cache['_cost']+=stored
            except (ValueError,TypeError,AttributeError,ezdxf.DXFError):
                # A tight display budget must never permanently poison this cache.
                return None
    template=cache[key]
    if template is None:return None
    parts,cost=template
    if budget and cost>budget.remaining:return None
    m=e.matrix44();u=m.transform_direction((1,0,0));v=m.transform_direction((0,1,0));t=m.transform((0,0,0))
    if abs(u.z)>1e-10 or abs(v.z)>1e-10:return None
    a,b,c,d,tx,ty=u.x,u.y,v.x,v.y,t.x,t.y
    scale=math.hypot(a,b);mirror=a*d-b*c<0
    def compatible(item):
        if item.get('approximate') and not math.isclose(scale,1,rel_tol=1e-12):return False
        if item.get('projected') and abs(e.dxf.zscale)!=1:return False
        if item.get('text') is not None and (mirror or e.dxf.extrusion.z<0):return False
        return all(compatible(child) for child in item.get('segments',[]))
    if instances is not None:
        _,_,(approximate,projected,text),_,bound=instances.summary(parts)
        if approximate and not math.isclose(scale,1,rel_tol=1e-12):return None
        if projected and abs(e.dxf.zscale)!=1:return None
        if text and (mirror or e.dxf.extrusion.z<0):return None
        # A conservative bound keeps out-of-range geometry on the existing
        # per-entity validation path, rather than failing the whole client scene.
        if max(abs(a)+abs(c),abs(b)+abs(d))*bound+max(abs(tx),abs(ty))>=1e12-1:return None
        if budget:budget.remaining-=cost
        return instances.instance(parts,[a,b,c,d,tx,ty])
    if not all(compatible(part) for part in parts):return None
    def xy(p):
        q=[a*p[0]+c*p[1]+tx,b*p[0]+d*p[1]+ty]
        if not all(math.isfinite(n) and abs(n)<1e12 for n in q):raise ValueError('좌표 범위 초과')
        return q
    def angle(value):
        r=math.radians(value);x,y=math.cos(r),math.sin(r)
        return math.degrees(math.atan2(b*x+d*y,a*x+c*y))%360
    def transform(item):
        result={**item,'id':None}
        for key in ('a','b','c'):
            if key in item:result[key]=xy(item[key])
        if 'r' in item:result['r']=item['r']*scale
        if item['type']=='ARC':
            start,end=angle(item['start']),angle(item['end'])
            result.update(start=end if mirror else start,end=start if mirror else end)
        if item['type'] in ('TEXT','MTEXT'):
            result.update(rotation=angle(item['rotation']),height=item['height']*scale)
        if 'pts' in item:result['pts']=[xy(p) for p in item['pts']]
        if 'segments' in item:result['segments']=[transform(child) for child in item['segments']]
        return result
    result=[transform(part) for part in parts]
    if budget:budget.remaining-=cost
    return result

def primitive(e, depth=0, ancestors=(), budget=None, instances=None):
    if budget is not None:budget.consume()
    d=e.dxf;k=e.dxftype()
    item={'id':d.get('handle',''),'type':k,'layer':d.get('layer','0'),'visible':not bool(d.get('invisible',0)),'colorIndex':int(d.get('color',256))}
    if 1<=item['colorIndex']<=255:
        item['color']=_aci_colors[item['colorIndex']]
    if d.hasattr('true_color'):item['color']='#'+format(int(d.true_color),'06x')
    if k=='LINE':
        item.update(a=xy(d.start),b=xy(d.end))
        if abs(d.start.z-d.end.z)>1e-8:item.update(projected=True,display_only=True)
    elif k in ('CIRCLE','ARC'):
        if not math.isfinite(d.radius) or not 0<d.radius<1e12:raise ValueError('반지름 범위 초과')
        if not planar(e):
            sampled(e,item);item.update(type='ELLIPSE',c=xy(e.ocs().to_wcs(d.center)),projected=True)
        else:
            ocs=e.ocs();item.update(c=xy(ocs.to_wcs(d.center)),r=float(d.radius))
            if k=='ARC':
                def world_angle(value):
                    a=math.radians(value);v=ocs.to_wcs((math.cos(a),math.sin(a),0))
                    return math.degrees(math.atan2(v.y,v.x))%360
                a,b=world_angle(d.start_angle),world_angle(d.end_angle)
                if ocs.uz.z<0:a,b=b,a
                item.update(start=a,end=b)
    elif k in ('LWPOLYLINE','POLYLINE'):
        if k=='POLYLINE' and not e.is_2d_polyline:
            if not e.is_3d_polyline:raise ValueError('메시 객체')
            item.update(pts=[xy(p) for p in e.points()],projected=True,display_only=True)
        else:
            segments=[]
            for v in e.virtual_entities():
                try:segments.append(primitive(v,budget=budget,instances=instances))
                except DisplayLimit:
                    if not segments:raise
                    item['partial']=True;break
            item.update(segments=segments,closed=bool(e.is_closed if k=='POLYLINE' else e.closed))
    elif k in ('INSERT','DIMENSION'):
        name=d.get('name','') if k=='INSERT' else ''
        if depth>=16 or name and name in ancestors:raise ValueError('블록 중첩 한도 또는 순환 참조')
        if k=='INSERT':
            fast=block_picture(e,depth,ancestors,budget,instances)
            if fast:
                item.update(segments=fast,display_only=True,omitted={})
                return item
        parts=[];omitted={}
        children=e.virtual_block_content if k=='DIMENSION' and e.is_virtual and e.virtual_block_content is not None else e.virtual_entities()
        for child in children:
            try:
                part=primitive(child,depth+1,ancestors+((name,) if name else ()),budget,instances)
                parts.append(part)
                if part.get('partial'):item['partial']=True
            except DisplayLimit:
                if not parts:raise
                item['partial']=True;break
            except (ValueError,TypeError,AttributeError,ezdxf.DXFError):
                kind=child.dxftype();omitted[kind]=omitted.get(kind,0)+1
        if not parts:raise ValueError('표시 가능한 블록 또는 치수 객체가 없습니다.')
        item.update(segments=parts,display_only=True,omitted=omitted)
    elif k=='POINT':item.update(c=xy(d.location))
    elif k in ('TEXT','MTEXT','ATTRIB','ATTDEF'):
        if k=='MTEXT':
            location=d.insert;rotation=e.get_rotation();height=d.get('char_height',1)
        else:
            ocs=e.ocs();location=ocs.to_wcs(d.insert);a=math.radians(d.get('rotation',0));v=ocs.to_wcs((math.cos(a),math.sin(a),0));rotation=math.degrees(math.atan2(v.y,v.x));height=d.get('height',1)
        item.update(type='MTEXT' if k=='MTEXT' else 'TEXT',c=xy(location),text=e.plain_text(),height=float(height),rotation=float(rotation),widthFactor=float(d.get('width',1)) if k!='MTEXT' else 1)
    elif k in ('ELLIPSE','SPLINE'):
        sampled(e,item)
        if k=='ELLIPSE':item['c']=xy(d.center)
    elif k in ('SOLID','TRACE'):
        item.update(pts=[xy(p) for p in e.wcs_vertices(close=True)],filled=True,display_only=True)
    elif k=='LEADER':item.update(pts=[xy(p) for p in e.vertices],display_only=True,approximate=bool(d.get('path_type',0)))
    else:raise ValueError('미지원 객체')
    return item

def layer_color(layer):
    if layer.dxf.hasattr('true_color'):return '#'+format(int(layer.dxf.true_color),'06x')
    return _aci_colors.get(abs(layer.dxf.get('color',7)),'#ffffff')

def serialize(s: Drawing, compact=False):
    entities, unsupported = [], dict(s.import_unsupported)
    truncated = s.preview
    projected=[0]
    budget=RenderBudget(s.display_limit)
    instances=_wire_pictures.setdefault(s.doc,PicturePool()) if compact else None
    pictures=_dwg_pictures.setdefault(s.doc,{}) if s.source_format=='dwg' and not compact else None
    s.display_partial_handles=set()
    for i, e in enumerate(s.doc.modelspace()):
        try:
            cached=pictures.get(e.dxf.handle) if pictures is not None else None
            if cached is not None and cached[1]<=budget.remaining:
                item,cost=cached
                budget.remaining-=cost
            else:
                before=budget.remaining
                item=primitive(e,budget=budget,instances=instances)
                if pictures is not None and not item.get('partial'):
                    pictures[e.dxf.handle]=(item,before-budget.remaining)
            entities.append(item)
            if item.get('partial'):s.display_partial_handles.add(item['id'])
            def omissions(value):
                if '$block' in value:
                    counts,n=instances.stats[value['$block']]
                    projected[0]+=n
                    for kind,count in counts.items():unsupported[kind]=unsupported.get(kind,0)+count
                    return
                if value.get("projected"):projected[0]+=1
                for kind,count in value.get('omitted',{}).items():
                    unsupported[kind]=unsupported.get(kind,0)+count
                for child in value.get('segments',[]):omissions(child)
            omissions(item)
        except DisplayLimit:
            truncated=True
            break
        except (ValueError, TypeError, AttributeError, ezdxf.DXFError):
            k = e.dxftype()
            unsupported[k] = unsupported.get(k, 0)+1
    truncated=truncated or budget.truncated
    s.view_limited=truncated
    warnings = list(s.warnings)
    if projected[0]:warnings.append('일부 3D 객체는 XY 평면에 투영해 표시합니다. 측정값은 2D 도면 거리이며 실제 3D 길이로 해석하지 마세요.')
    if unsupported:
        warnings.append('DWG 미지원 객체가 화면에서 생략되었습니다. 화면만으로 원본 전체를 판단하지 마세요. 원본 DWG 파일은 변경하지 않습니다.' if s.source_format=='dwg' else '미표시 객체는 원본 DXF 문서에 유지됩니다. 화면만으로 도면 전체를 판단하지 마세요.')
    if truncated:
        warnings.insert(0,f'부분 미리보기: 화면 표시·처리 한도에 따라 도면 일부만 보입니다(표시 요소 예산 {s.display_limit:,}개, 중첩 객체 포함). 전체 도면 인쇄가 아니며, 부분 표시된 폴리라인의 전체 길이는 측정할 수 없습니다.')
    result=dict(entities=entities, unsupported=unsupported, total=len(s.doc.modelspace())+s.unrendered_roots, units=int(s.doc.units),
                filename=s.name, source_format=s.source_format, preview=truncated, history_limit=s.history_limit, layers=[{'name':l.dxf.name,'visible':not l.is_off() and not l.is_frozen(),'locked':l.is_locked(),'color':layer_color(l)} for l in s.doc.layers],
                warnings=warnings, truncated=truncated, revision=s.revision, can_undo=bool(s.undo), can_redo=bool(s.redo))
    if instances is not None:
        definitions=instances.reachable(entities)
        if definitions:result['blockPictures']=definitions
    return result

def edit_document(s, payload, compact=False):
    if payload.revision is not None and payload.revision != s.revision:
        raise CADProblem(409, '도면 버전이 변경되었습니다. 다시 열어주세요.')
    if s.view_limited and payload.op in ('add_line','add_circle','copy'):
        raise CADProblem(400,'부분 미리보기에서는 객체 추가·복사를 지원하지 않습니다. 표시된 개별 객체의 이동·삭제·좌표 수정은 가능합니다.')
    candidate = deepcopy(s.doc)
    msp = candidate.modelspace()
    try:
        if payload.layer not in candidate.layers:
            raise ValueError('없는 레이어입니다.')
        if payload.op in ('add_line', 'add_circle'):
            if candidate.layers.get(payload.layer).is_locked():
                raise ValueError('잠긴 레이어입니다.')
            attrs = {'layer': payload.layer}
            if payload.op == 'add_line':
                if payload.x1 == payload.x2 and payload.y1 == payload.y2:
                    raise ValueError('선의 길이는 0보다 커야 합니다.')
                msp.add_line((payload.x1, payload.y1), (payload.x2, payload.y2), dxfattribs=attrs)
            else:
                msp.add_circle((payload.x1, payload.y1), payload.radius, dxfattribs=attrs)
        else:
            handles = list(dict.fromkeys(payload.handles or ([payload.handle] if payload.handle else [])))
            if not handles:
                raise ValueError('먼저 객체를 선택하세요.')
            for handle in handles:
                if handle in s.display_partial_handles:raise ValueError('일부만 표시된 객체는 수정할 수 없습니다. 개별 객체를 선택하세요.')
                e = candidate.entitydb.get(handle)
                if e is None or not e.is_alive or e not in msp:
                    raise ValueError('객체를 찾지 못했습니다.')
                if e.dxftype() not in EDITABLE or not planar(e) or e.dxftype()=='LINE' and abs(e.dxf.start.z-e.dxf.end.z)>1e-8:
                    raise ValueError('이 단계에서는 이 객체를 편집할 수 없습니다.')
                if candidate.layers.get(e.dxf.layer).is_locked():
                    raise ValueError('잠긴 레이어입니다.')
                if payload.op == 'delete':
                    msp.delete_entity(e)
                elif payload.op in ('move', 'copy'):
                    if payload.op == 'copy':
                        e = e.copy()
                        msp.add_entity(e)
                    e.translate(payload.dx, payload.dy, 0)
                elif payload.op == 'set_line' and e.dxftype() == 'LINE':
                    if (payload.x1, payload.y1) == (payload.x2, payload.y2):
                        raise ValueError('선의 길이는 0보다 커야 합니다.')
                    e.dxf.start = (payload.x1, payload.y1, e.dxf.start.z)
                    e.dxf.end = (payload.x2, payload.y2, e.dxf.end.z)
                elif payload.op == 'set_circle' and e.dxftype() == 'CIRCLE':
                    from ezdxf.math import Vec3
                    center=e.ocs().to_wcs(e.dxf.center)
                    e.dxf.center=e.ocs().from_wcs(Vec3(payload.x1,payload.y1,center.z))
                    e.dxf.radius = payload.radius
                else:
                    raise ValueError('객체 형식과 수정 작업이 맞지 않습니다.')
                if payload.op != 'delete':
                    primitive(e)
    except (ValueError, ezdxf.DXFError) as exc:
        raise CADProblem(400, str(exc))
    s.undo.append(s.doc)
    s.undo = s.undo[-s.history_limit:]
    s.redo.clear()
    if s.source_format=='dwg':
        changed=set(payload.handles or ([payload.handle] if payload.handle else []))
        _dwg_pictures[candidate]={key:value for key,value in _dwg_pictures.get(s.doc,{}).items() if key not in changed}
    if s.doc in _block_pictures:_block_pictures[candidate]=dict(_block_pictures[s.doc])
    if s.doc in _wire_pictures:_wire_pictures[candidate]=_wire_pictures[s.doc]
    s.doc = candidate
    s.revision += 1
    return serialize(s,compact=compact)
