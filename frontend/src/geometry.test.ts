import { test } from "node:test";
import assert from "node:assert/strict";
import {
  distance,
  toWorld,
  toScreen,
  zoom,
  fit,
  snap,
  length,
  angle,
  pick,
  type Entity,
} from "./geometry";
const line: Entity = {
  id: "l",
  type: "LINE",
  layer: "0",
  a: [0, 0],
  b: [30, 40],
};
const circle: Entity = {
  id: "c",
  type: "CIRCLE",
  layer: "0",
  c: [100, 100],
  r: 20,
};
const arc: Entity = {
  id: "a",
  type: "ARC",
  layer: "0",
  c: [0, 0],
  r: 10,
  start: 350,
  end: 10,
};
const close = (a: number, b: number) =>
  assert.ok(Math.abs(a - b) < 1e-8, `${a} != ${b}`);
test("world/screen round trip at large and negative coordinates", () => {
  const v = { x: 800, y: 500, scale: 0.002 };
  const p: [number, number] = [1e6, -2e6];
  assert.deepEqual(toWorld(toScreen(p, v), v), p);
});
test("wheel zoom preserves cursor world position", () => {
  const v = { x: 300, y: 200, scale: 2 },
    p: [number, number] = [720, 540];
  const before = toWorld(p, v);
  const after = toWorld(p, zoom(v, p, 3));
  close(before[0], after[0]);
  close(before[1], after[1]);
});
test("distance is independent of display scale", () => {
  close(distance(line.a!, line.b!), 50);
  for (const scale of [0.001, 1, 10000]) {
    const v = { x: 52, y: -20, scale };
    close(
      distance(
        toWorld(toScreen(line.a!, v), v),
        toWorld(toScreen(line.b!, v), v),
      ),
      50,
    );
  }
});
test("endpoint and midpoint snaps use analytic vertices", () => {
  assert.equal(snap([30.1, 40.1], [line], 1)?.kind, "끝점");
  assert.deepEqual(snap([15.1, 20.1], [line], 1)?.point, [15, 20]);
  assert.equal(snap([9, 1], [line], 1), undefined);
});
test("circle center snap, no tessellation pseudo endpoints", () => {
  assert.deepEqual(snap([100.1, 100], [circle], 1)?.point, [100, 100]);
  assert.equal(snap([120, 100], [circle], 1), undefined);
});
test("arc final endpoint snaps even at angle wrap", () => {
  const p: [number, number] = [
    10 * Math.cos(Math.PI / 18),
    10 * Math.sin(Math.PI / 18),
  ];
  const result = snap(p, [arc], 0.1)!;
  assert.equal(result.kind, "끝점");
  close(distance(p, result.point), 0);
});
test("polyline bulge length uses exact arc length", () => {
  const poly: Entity = {
    id: "p",
    type: "LWPOLYLINE",
    layer: "0",
    segments: [{ ...arc, start: 0, end: 180 }, line],
  };
  close(length(poly), Math.PI * 10 + 50);
});
test("angles and radius lengths", () => {
  close(angle({ ...line, b: [10, 0] }, { ...line, b: [0, 10] }), 90);
  close(length(circle), 40 * Math.PI);
  close(length(arc), (10 * Math.PI) / 9);
});
test("fit handles 150000 points without argument spread overflow", () => {
  const lines = Array.from(
    { length: 75000 },
    (_, i) => ({ ...line, a: [i, 0], b: [i, 1] }) as Entity,
  );
  const v = fit(lines, 800, 600);
  assert.ok(v.scale > 0);
  assert.ok(toScreen([0, 0], v)[0] >= 39);
  assert.ok(toScreen([74999, 1], v)[0] <= 761);
});
test("fit empty and point drawings are finite", () => {
  for (const es of [
    [],
    [{ id: "p", type: "POINT", layer: "0", c: [0, 0] } as Entity],
  ]) {
    const v = fit(es, 30, 20);
    assert.ok(Number.isFinite(v.scale));
  }
});
test("hidden layers cannot snap or select when filtered", () => {
  const visible = [line, circle].filter((e) => e.id !== "c");
  assert.equal(snap([100, 100], visible, 1), undefined);
  assert.equal(pick([120, 100], visible, 1), undefined);
  assert.equal(pick([120, 100], [circle], 1)?.id, "c");
});
