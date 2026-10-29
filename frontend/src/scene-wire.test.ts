import { test } from "node:test";
import assert from "node:assert/strict";
import { expandBlocks, SceneResponse } from "./scene-wire";
import { snap, length, type Entity } from "./geometry";
import { drawingSvg } from "./printing";

test("nested block matrices preserve roots, metadata, lines, circles and mirrored arcs", () => {
  const result = expandBlocks({
    filename: "한글.dwg",
    units: 4,
    revision: 7,
    entities: [
      {
        id: "root",
        type: "INSERT",
        layer: "A",
        segments: [{ $block: "outer", matrix: [0, 2, -2, 0, 100, 200] }],
      },
    ],
    blockPictures: {
      outer: [
        {
          id: null,
          type: "INSERT",
          layer: "0",
          segments: [{ $block: "leaf", matrix: [-1, 0, 0, 1, 10, 20] }],
        },
      ],
      leaf: [
        { id: "local", type: "LINE", layer: "0", a: [1, 2], b: [4, 2] },
        { id: null, type: "CIRCLE", layer: "0", c: [2, 3], r: 2 },
        {
          id: null,
          type: "ARC",
          layer: "0",
          c: [0, 0],
          r: 1,
          start: 0,
          end: 90,
        },
      ],
    },
  });
  assert.equal(result.filename, "한글.dwg");
  assert.equal(result.revision, 7);
  assert.equal("blockPictures" in result, false);
  const root = result.entities[0] as unknown as Entity;
  assert.equal(root.id, "root");
  assert.equal(root.layer, "A");
  const [line, circle, arc] = root.segments![0].segments!;
  assert.deepEqual(line.a, [56, 218]);
  assert.deepEqual(line.b, [56, 212]);
  assert.equal(line.id, null);
  assert.deepEqual(circle.c, [54, 216]);
  assert.equal(circle.r, 4);
  assert.equal(arc.start, 180);
  assert.equal(arc.end, 270);
  assert.equal(length(line), 6);
  assert.deepEqual(snap([56.1, 218.1], [root], 1)?.point, [56, 218]);
  assert.match(drawingSvg([root]), /<circle /);
});

test("text size/rotation, sampled curves, filled geometry and reused definitions are independent", () => {
  const wire = {
    entities: [
      {
        id: "a",
        type: "INSERT",
        layer: "0",
        segments: [{ $block: "p", matrix: [0, 2, -2, 0, 100, 200] }],
      },
      {
        id: "b",
        type: "INSERT",
        layer: "0",
        segments: [{ $block: "p", matrix: [1, 0, 0, 1, 0, 0] }],
      },
    ],
    blockPictures: {
      p: [
        {
          id: null,
          type: "MTEXT",
          layer: "0",
          c: [10, 20],
          height: 1.5,
          rotation: 30,
          widthFactor: 0.75,
          text: "label",
        },
        {
          id: null,
          type: "SPLINE",
          layer: "0",
          pts: [
            [0, 0],
            [1, 2],
            [2, 0],
          ],
          approximate: true,
        },
        {
          id: null,
          type: "SOLID",
          layer: "0",
          pts: [
            [0, 0],
            [1, 0],
            [0, 1],
            [0, 0],
          ],
          filled: true,
        },
      ],
    },
  };
  const result = expandBlocks(wire) as unknown as { entities: Entity[] };
  const [text, curve, solid] = result.entities[0].segments!;
  assert.deepEqual(text.c, [60, 220]);
  assert.equal(text.height, 3);
  assert.ok(Math.abs(text.rotation! - 120) < 1e-10);
  assert.equal(text.widthFactor, 0.75);
  assert.deepEqual(curve.pts, [
    [100, 200],
    [96, 202],
    [100, 204],
  ]);
  assert.equal(solid.filled, true);
  curve.pts![0][0] = 999;
  assert.deepEqual(result.entities[1].segments![1].pts![0], [0, 0]);
  assert.deepEqual(wire.blockPictures.p[1].pts![0], [0, 0]);
});

test("unknown, cyclic and nonfinite block references are rejected", () => {
  assert.throws(
    () =>
      expandBlocks({
        entities: [{ $block: "missing", matrix: [1, 0, 0, 1, 0, 0] }],
        blockPictures: {},
      }),
    /블록/,
  );
  assert.throws(
    () =>
      expandBlocks({
        entities: [{ $block: "a", matrix: [1, 0, 0, 1, 0, 0] }],
        blockPictures: { a: [{ $block: "a", matrix: [1, 0, 0, 1, 0, 0] }] },
      }),
    /블록/,
  );
  assert.throws(
    () =>
      expandBlocks({
        entities: [{ $block: "a", matrix: [1, 0, 0, 1, NaN, 0] }],
        blockPictures: { a: [] },
      }),
    /블록/,
  );
});

test("regular responses pass through and cloning preserves scene JSON decoding", async () => {
  const error = { detail: "입력 오류" };
  assert.equal(expandBlocks(error), error);
  const wire = {
    filename: "test.dwg",
    entities: [
      {
        id: "root",
        type: "INSERT",
        layer: "0",
        segments: [{ $block: "a", matrix: [1, 0, 0, 1, 10, 20] }],
      },
    ],
    blockPictures: {
      a: [{ id: null, type: "LINE", layer: "0", a: [0, 0], b: [3, 4] }],
    },
  };
  const response = new SceneResponse(
    new TextEncoder().encode(JSON.stringify(wire)),
    { status: 200 },
  );
  const copy = response.clone();
  const a = await response.json(),
    b = await copy.json();
  assert.deepEqual(a, b);
  assert.equal(response.bodyUsed, true);
  assert.equal(length(a.entities[0].segments[0]), 5);
  assert.deepEqual(
    await new SceneResponse(JSON.stringify(error), { status: 422 }).json(),
    error,
  );
});
