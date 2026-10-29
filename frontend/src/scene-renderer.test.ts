import { test } from "node:test";
import assert from "node:assert/strict";
import { buildScene, paintScene } from "./scene-renderer";
import type { Entity } from "./geometry";
class FakePath {
  moveTo() {}
  lineTo() {}
  arc() {}
  closePath() {}
}
Object.assign(globalThis, { Path2D: FakePath });
test("spatial tiles retain every entity and cull only tiles outside the view", () => {
  const entities: Entity[] = Array.from({ length: 30001 }, (_, i) => ({
    id: String(i),
    type: "LINE",
    layer: "A",
    a: [i * 10, 0],
    b: [i * 10 + 5, 10],
  }));
  // A long line crosses the view even though its centre belongs to a distant tile.
  entities.push({
    id: "long",
    type: "LINE",
    layer: "A",
    a: [-100, 20],
    b: [400000, 20],
  });
  const scene = buildScene(entities, [{ name: "A", color: "#ff0000" }], []);
  assert.equal(scene.elements, 30002);
  let red = false;
  const ctx = {
    setTransform() {},
    stroke() {
      if (this.strokeStyle === "#ff0000") red = true;
    },
    fill() {},
    strokeStyle: "",
    lineWidth: 0,
  } as unknown as CanvasRenderingContext2D;
  const drawn = paintScene(
    ctx,
    scene,
    { x: 0, y: 100, scale: 1 },
    1000,
    200,
    1,
  );
  assert.ok(drawn > 0 && drawn < scene.tiles.length);
  assert.ok(red);
});
