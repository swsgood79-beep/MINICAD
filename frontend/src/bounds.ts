import type { Entity, Point, View } from "./geometry";
export type Bounds = [number, number, number, number];
const cache = new WeakMap<Entity, Bounds>();
export const intersects = (a: Bounds, b: Bounds) =>
  a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
export function entityBounds(e: Entity): Bounds {
  const old = cache.get(e);
  if (old) return old;
  const box: Bounds = [Infinity, Infinity, -Infinity, -Infinity];
  const point = (p: Point) => {
    box[0] = Math.min(box[0], p[0]);
    box[1] = Math.min(box[1], p[1]);
    box[2] = Math.max(box[2], p[0]);
    box[3] = Math.max(box[3], p[1]);
  };
  if (e.segments) {
    for (const child of e.segments) {
      const b = entityBounds(child);
      point([b[0], b[1]]);
      point([b[2], b[3]]);
    }
  } else if (e.pts) {
    for (const p of e.pts) point(p);
  } else if (e.a && e.b) {
    point(e.a);
    point(e.b);
  } else if (e.c) {
    if (e.r && e.type === "ARC") {
      let a = ((e.start ?? 0) * Math.PI) / 180,
        b = ((e.end ?? 360) * Math.PI) / 180;
      while (b <= a) b += 2 * Math.PI;
      const at = (t: number): Point => [
        e.c![0] + e.r! * Math.cos(t),
        e.c![1] + e.r! * Math.sin(t),
      ];
      point(at(a));
      point(at(b));
      for (let k = Math.ceil(a / (Math.PI / 2)); (k * Math.PI) / 2 < b; k++)
        point(at((k * Math.PI) / 2));
    } else if (e.r) {
      point([e.c[0] - e.r, e.c[1] - e.r]);
      point([e.c[0] + e.r, e.c[1] + e.r]);
    } else if (e.text) {
      const h = e.height ?? 1,
        lines = e.text.split("\n"),
        w =
          lines.reduce(
            (max, line) =>
              Math.max(
                max,
                [...line].reduce(
                  (n, c) => n + (c.charCodeAt(0) > 255 ? 1 : 0.65),
                  0,
                ),
              ),
            0,
          ) *
          h *
          (e.widthFactor ?? 1),
        low = -((lines.length - 1) * 1.3 + 0.2) * h,
        high = 0.8 * h,
        a = ((e.rotation ?? 0) * Math.PI) / 180;
      for (const [x, y] of [
        [0, low],
        [w, low],
        [w, high],
        [0, high],
      ])
        point([
          e.c[0] + x * Math.cos(a) - y * Math.sin(a),
          e.c[1] + x * Math.sin(a) + y * Math.cos(a),
        ]);
    } else point(e.c);
  }
  cache.set(e, box);
  return box;
}
export function sceneBounds(entities: Entity[]): Bounds {
  const b: Bounds = [Infinity, Infinity, -Infinity, -Infinity];
  for (const e of entities) {
    const x = entityBounds(e);
    b[0] = Math.min(b[0], x[0]);
    b[1] = Math.min(b[1], x[1]);
    b[2] = Math.max(b[2], x[2]);
    b[3] = Math.max(b[3], x[3]);
  }
  return b;
}
export const nearBounds = (p: Point, t: number): Bounds => [
  p[0] - t,
  p[1] - t,
  p[0] + t,
  p[1] + t,
];
export function viewBounds(v: View, w: number, h: number): Bounds {
  return [
    -v.x / v.scale,
    (v.y - h) / v.scale,
    (w - v.x) / v.scale,
    v.y / v.scale,
  ];
}
