import { entityBounds, sceneBounds, intersects, nearBounds } from "./bounds";
export type Point = [number, number];
export type Entity = {
  id: string;
  type: string;
  layer: string;
  a?: Point;
  b?: Point;
  c?: Point;
  r?: number;
  start?: number;
  end?: number;
  segments?: Entity[];
  closed?: boolean;
  partial?: boolean;
  pts?: Point[];
  filled?: boolean;
  projected?: boolean;
  approximate?: boolean;
  display_only?: boolean;
  visible?: boolean;
  colorIndex?: number;
  color?: string;
  widthFactor?: number;
  text?: string;
  height?: number;
  rotation?: number;
};
export type View = { x: number; y: number; scale: number };
export const distance = (a: Point, b: Point) =>
  Math.hypot(a[0] - b[0], a[1] - b[1]);
export const toScreen = (p: Point, v: View): Point => [
  v.x + p[0] * v.scale,
  v.y - p[1] * v.scale,
];
export const toWorld = (p: Point, v: View): Point => [
  (p[0] - v.x) / v.scale,
  (v.y - p[1]) / v.scale,
];
export function zoom(v: View, p: Point, factor: number): View {
  const w = toWorld(p, v),
    s = Math.max(1e-8, Math.min(1e8, v.scale * factor));
  return { x: p[0] - w[0] * s, y: p[1] + w[1] * s, scale: s };
}
export const sweep = (e: Entity) => {
  const a = ((e.start ?? 0) * Math.PI) / 180;
  let b = ((e.end ?? 360) * Math.PI) / 180;
  while (b <= a) b += Math.PI * 2;
  return [a, b];
};
export const arcPoint = (e: Entity, t: number): Point => [
  e.c![0] + e.r! * Math.cos(t),
  e.c![1] + e.r! * Math.sin(t),
];
export function paths(e: Entity): Point[][] {
  if (e.segments) return e.segments.flatMap(paths);
  if (e.pts) return [e.pts];
  if (e.type === "LINE") return [[e.a!, e.b!]];
  if (e.type === "POINT" || e.type === "TEXT" || e.type === "MTEXT")
    return [[e.c!]];
  if (e.type === "ARC" || e.type === "CIRCLE") {
    const [a, b] = e.type === "CIRCLE" ? [0, 2 * Math.PI] : sweep(e);
    const n = Math.max(8, Math.ceil((b - a) * 32));
    return [
      Array.from({ length: n + 1 }, (_, i) =>
        arcPoint(e, a + ((b - a) * i) / n),
      ),
    ];
  }
  return [];
}
export function length(e: Entity): number {
  if (e.segments) return e.segments.reduce((n, s) => n + length(s), 0);
  if (e.pts)
    return e.pts.slice(1).reduce((n, p, i) => n + distance(e.pts![i], p), 0);
  if (e.type === "LINE") return distance(e.a!, e.b!);
  if (e.type === "ARC") {
    const [a, b] = sweep(e);
    return e.r! * (b - a);
  }
  if (e.type === "CIRCLE") return 2 * Math.PI * e.r!;
  return 0;
}
export function fit(entities: Entity[], width: number, height: number): View {
  const [x0, y0, x1, y1] = sceneBounds(entities);
  if (!Number.isFinite(x0)) return { x: width / 2, y: height / 2, scale: 1 };
  const scale = Math.max(
    1e-8,
    Math.min(
      1e8,
      Math.min(
        Math.max(1, width - 80) / Math.max(1, x1 - x0),
        Math.max(1, height - 80) / Math.max(1, y1 - y0),
      ),
    ),
  );
  return {
    x: width / 2 - ((x0 + x1) / 2) * scale,
    y: height / 2 + ((y0 + y1) / 2) * scale,
    scale,
  };
}
export function segmentDistance(p: Point, a: Point, b: Point) {
  const dx = b[0] - a[0],
    dy = b[1] - a[1],
    d = dx * dx + dy * dy;
  const t = d
    ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d))
    : 0;
  return distance(p, [a[0] + t * dx, a[1] + t * dy]);
}
export function pick(
  p: Point,
  entities: Entity[],
  tolerance: number,
): Entity | undefined {
  let best: Entity | undefined,
    d = tolerance;
  const region = nearBounds(p, tolerance);
  const visit = (e: Entity, owner: Entity) => {
    if (!intersects(entityBounds(e), region)) return;
    if (e.segments) {
      for (const child of e.segments) visit(child, owner);
      return;
    }
    let n = Infinity;
    if (e.type === "CIRCLE") n = Math.abs(distance(p, e.c!) - e.r!);
    else if (e.type === "ARC") {
      const [a, b] = sweep(e);
      let t = Math.atan2(p[1] - e.c![1], p[0] - e.c![0]);
      while (t < a) t += Math.PI * 2;
      n =
        t <= b
          ? Math.abs(distance(p, e.c!) - e.r!)
          : Math.min(distance(p, arcPoint(e, a)), distance(p, arcPoint(e, b)));
    } else
      for (const path of paths(e)) {
        if (path.length === 1) n = Math.min(n, distance(p, path[0]));
        for (let i = 1; i < path.length; i++)
          n = Math.min(n, segmentDistance(p, path[i - 1], path[i]));
      }
    if (n < d) {
      d = n;
      best = owner;
    }
  };
  for (const e of entities) visit(e, e);
  return best;
}
export type Snap = { point: Point; kind: string };
// A group's drawn bounds need not contain the centres of its short arcs.
// Cache a separate search bound so pruning never hides a valid centre snap.
const snapBoxes = new WeakMap<Entity, ReturnType<typeof entityBounds>>();
function snapBounds(e: Entity): ReturnType<typeof entityBounds> {
  const cached = snapBoxes.get(e);
  if (cached) return cached;
  const box = [...entityBounds(e)] as ReturnType<typeof entityBounds>;
  if (e.c) {
    box[0] = Math.min(box[0], e.c[0]);
    box[1] = Math.min(box[1], e.c[1]);
    box[2] = Math.max(box[2], e.c[0]);
    box[3] = Math.max(box[3], e.c[1]);
  }
  for (const child of e.segments ?? []) {
    const b = snapBounds(child);
    box[0] = Math.min(box[0], b[0]);
    box[1] = Math.min(box[1], b[1]);
    box[2] = Math.max(box[2], b[2]);
    box[3] = Math.max(box[3], b[3]);
  }
  snapBoxes.set(e, box);
  return box;
}
export function snap(
  p: Point,
  entities: Entity[],
  tolerance: number,
): Snap | undefined {
  let best: Snap | undefined,
    d = tolerance;
  const consider = (point: Point, kind: string) => {
    const n = distance(p, point);
    if (n < d) {
      d = n;
      best = { point, kind };
    }
  };
  const region = nearBounds(p, tolerance);
  const visit = (e: Entity) => {
    // The centre can lie outside the tight bounds of a short arc.
    if (
      (e.type === "CIRCLE" || e.type === "ARC" || e.type === "ELLIPSE") &&
      e.c
    )
      consider(e.c, "중심점");
    if (!intersects(snapBounds(e), region)) return;
    if (e.segments) {
      e.segments.forEach(visit);
      return;
    }
    if (e.type === "LINE") {
      consider(e.a!, "끝점");
      consider(e.b!, "끝점");
      consider([(e.a![0] + e.b![0]) / 2, (e.a![1] + e.b![1]) / 2], "중간점");
    }
    if (e.type === "ARC") {
      const [a, b] = sweep(e);
      consider(arcPoint(e, a), "끝점");
      consider(arcPoint(e, b), "끝점");
    }
    if (e.type === "POINT") consider(e.c!, "점");
    if (e.pts && !e.approximate && !e.projected)
      for (const point of e.pts) consider(point, "끝점");
  };
  entities.forEach(visit);
  return best;
}
export function angle(a: Entity, b: Entity) {
  const u = [a.b![0] - a.a![0], a.b![1] - a.a![1]],
    v = [b.b![0] - b.a![0], b.b![1] - b.a![1]];
  return (
    (Math.atan2(
      Math.abs(u[0] * v[1] - u[1] * v[0]),
      u[0] * v[0] + u[1] * v[1],
    ) *
      180) /
    Math.PI
  );
}

/** Layer 0 inside a block inherits the insertion layer; hidden children must not snap or print. */
export function visibleEntities(
  entities: Entity[],
  hidden: Set<string>,
  parentLayer?: string,
): Entity[] {
  return entities.flatMap((e) => {
    if (e.visible === false) return [];
    const layer = parentLayer && e.layer === "0" ? parentLayer : e.layer;
    if (hidden.has(layer)) return [];
    if (!e.segments) return [e];
    const segments = visibleEntities(e.segments, hidden, layer);
    return segments.length ? [{ ...e, segments }] : [];
  });
}
