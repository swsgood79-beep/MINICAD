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
  if (e.type === "LINE") return distance(e.a!, e.b!);
  if (e.type === "ARC") {
    const [a, b] = sweep(e);
    return e.r! * (b - a);
  }
  if (e.type === "CIRCLE") return 2 * Math.PI * e.r!;
  return 0;
}
export function fit(entities: Entity[], width: number, height: number): View {
  let x0 = Infinity,
    y0 = Infinity,
    x1 = -Infinity,
    y1 = -Infinity;
  const visit = (e: Entity) => {
    if (e.segments) {
      e.segments.forEach(visit);
      return;
    }
    const ps = paths(e).flat();
    if (e.c && e.r)
      ps.push([e.c[0] - e.r, e.c[1] - e.r], [e.c[0] + e.r, e.c[1] + e.r]);
    for (const [x, y] of ps) {
      x0 = Math.min(x0, x);
      x1 = Math.max(x1, x);
      y0 = Math.min(y0, y);
      y1 = Math.max(y1, y);
    }
  };
  entities.forEach(visit);
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
  for (const e of entities)
    for (const path of paths(e)) {
      if (path.length === 1) {
        const n = distance(p, path[0]);
        if (n < d) {
          d = n;
          best = e;
        }
      }
      for (let i = 1; i < path.length; i++) {
        const n = segmentDistance(p, path[i - 1], path[i]);
        if (n < d) {
          d = n;
          best = e;
        }
      }
    }
  return best;
}
export type Snap = { point: Point; kind: string };
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
  const visit = (e: Entity) => {
    if (e.segments) {
      e.segments.forEach(visit);
      return;
    }
    if (e.type === "LINE") {
      consider(e.a!, "끝점");
      consider(e.b!, "끝점");
      consider([(e.a![0] + e.b![0]) / 2, (e.a![1] + e.b![1]) / 2], "중간점");
    }
    if (e.type === "CIRCLE" || e.type === "ARC") consider(e.c!, "중심점");
    if (e.type === "ARC") {
      const [a, b] = sweep(e);
      consider(arcPoint(e, a), "끝점");
      consider(arcPoint(e, b), "끝점");
    }
    if (e.type === "POINT") consider(e.c!, "점");
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
