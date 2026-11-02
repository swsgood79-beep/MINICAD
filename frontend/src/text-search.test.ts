import { test } from "node:test";
import assert from "node:assert/strict";
import { findText } from "./text-search";
import type { Entity } from "./geometry";
const text: Entity = { id: "t", type: "MTEXT", layer: "0", c: [10, 20], text: "회의실 OFFICE\n출입구" };
test("finds Korean and case insensitive literal substrings, ignoring empty queries", () => {
  assert.equal(findText([text], "회의").length, 1);
  assert.equal(findText([text], "office").length, 1);
  assert.equal(findText([text], "없는 단어").length, 0);
  assert.equal(findText([text], "  ").length, 0);
});
test("nested block matches retain the selectable parent ID", () => {
  const matches = findText([{ id: "block", type: "INSERT", layer: "0", segments: [text] }, { ...text, id: "other" }], "출입구");
  assert.deepEqual(matches.map(m => m.ownerId), ["block", "other"]);
  assert.equal(matches[0].entity, text);
});
