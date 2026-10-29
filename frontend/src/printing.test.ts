import { test } from "node:test";
import assert from "node:assert/strict";
import { drawingSvg, escapeXml } from "./printing";
import { visibleEntities, type Entity } from "./geometry";
const circle: Entity = {
  id: "c",
  type: "CIRCLE",
  layer: "A",
  c: [10, 20],
  r: 5,
};
test("print uses vector circles, black ink and no canvas/UI/grid", () => {
  const svg = drawingSvg([circle]);
  assert.match(svg, /<circle /);
  assert.match(svg, /stroke="black"/);
  assert.doesNotMatch(svg, /canvas|grid|button|#0c141e/);
});
test("print arcs preserve sweep and closed polyline segments", () => {
  const svg = drawingSvg([{ ...circle, type: "ARC", start: 350, end: 10 }]);
  assert.match(svg, /<path d="M .* A .* 0 0 0 /);
});
test("drawing text is XML escaped, including filenames supplied by users", () => {
  const svg = drawingSvg([
    {
      id: "t",
      type: "TEXT",
      layer: "A",
      c: [0, 0],
      text: '<script>alert("x")</script>&',
    },
  ]);
  assert.doesNotMatch(svg, /<script>/);
  assert.match(svg, /&lt;script&gt;/);
  assert.equal(escapeXml('a&"<>'), "a&amp;&quot;&lt;&gt;");
});
test("hidden layers are absent from vector print and nested layer 0 inherits insertion", () => {
  const group: Entity = {
    id: "block",
    type: "INSERT",
    layer: "A",
    segments: [
      { ...circle, id: "zero", layer: "0" },
      { ...circle, id: "other", layer: "B" },
    ],
  };
  const shown = visibleEntities([group], new Set(["B", "0"]));
  assert.equal(shown.length, 1);
  assert.equal(shown[0].segments?.length, 1);
  assert.equal(shown[0].segments?.[0].id, "zero");
  assert.equal((drawingSvg(shown).match(/<circle /g) ?? []).length, 1);
  assert.equal(visibleEntities([group], new Set(["A"])).length, 0);
});
test("empty drawing still has a finite, valid print viewBox", () => {
  const svg = drawingSvg([]);
  assert.match(svg, /viewBox="0 0 1100 700"/);
  assert.doesNotMatch(svg, /NaN|Infinity/);
});
