import type { Entity } from "./geometry";

/** Return text objects in drawing order, including text inside blocks. */
export function findText(entities: Entity[], query: string) {
  const needle = query.trim().normalize("NFC").toLocaleLowerCase();
  const matches: { entity: Entity; ownerId: string }[] = [];
  if (!needle) return matches;
  function visit(entity: Entity, ownerId: string) {
    if (entity.text?.normalize("NFC").toLocaleLowerCase().includes(needle))
      matches.push({ entity, ownerId });
    entity.segments?.forEach(child => visit(child, ownerId));
  }
  entities.forEach(entity => visit(entity, entity.id));
  return matches;
}
