import { test } from "node:test";
import assert from "node:assert/strict";
import { entityBounds, sceneBounds, intersects, viewBounds } from "./bounds";
import { fit, toScreen, snap, type Entity } from "./geometry";
const line = (id: string, x: number, y = 0): Entity => ({
  id,
  type: "LINE",
  layer: "0",
  a: [x, y],
  b: [x + 100, y],
});
test("full fit includes the last object beyond the former 30000 prefix", () => {
  const entities = Array.from({ length: 30001 }, (_, i) =>
    line(String(i), i === 30000 ? 50000 : 0),
  );
  assert.deepEqual(sceneBounds(entities), [0, 0, 50100, 0]);
  const v = fit(entities, 1000, 700);
  assert.ok(toScreen([50100, 0], v)[0] <= 960);
});
test("tight arc bounds include crossing quadrants and centre snapping remains possible", () => {
  const arc: Entity = {
    id: "arc",
    type: "ARC",
    layer: "0",
    c: [100, 200],
    r: 10,
    start: 350,
    end: 10,
  };
  const b = entityBounds(arc);
  assert.ok(b[0] > 109 && b[2] === 110);
  assert.deepEqual(snap([100.1, 200.1], [arc], 1), {
    kind: "중심점",
    point: [100, 200],
  });
  const group: Entity = {
    id: "block",
    type: "INSERT",
    layer: "0",
    segments: [arc],
  };
  assert.deepEqual(snap([100.1, 200.1], [group], 1), {
    kind: "중심점",
    point: [100, 200],
  });
});
test("nested curves, text rotation and viewport intersection have finite bounds", () => {
  const group: Entity = {
    id: "b",
    type: "INSERT",
    layer: "0",
    segments: [
      line("l", -20),
      {
        id: "s",
        type: "SPLINE",
        layer: "0",
        pts: [
          [-40, -50],
          [200, 300],
        ],
      },
    ],
  };
  assert.deepEqual(entityBounds(group), [-40, -50, 200, 300]);
  const text: Entity = {
    id: "t",
    type: "TEXT",
    layer: "0",
    c: [0, 0],
    text: "ABC",
    height: 10,
    rotation: 90,
  };
  const b = entityBounds(text);
  assert.ok(b.every(Number.isFinite));
  assert.ok(b[3] > 19);
  assert.ok(
    intersects(
      entityBounds(group),
      viewBounds({ x: 0, y: 100, scale: 1 }, 100, 100),
    ),
  );
  assert.equal(
    intersects(
      [1000, 1000, 1100, 1100],
      viewBounds({ x: 0, y: 100, scale: 1 }, 100, 100),
    ),
    false,
  );
});
