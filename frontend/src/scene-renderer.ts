import {
  type Entity,
  type Point,
  type View,
  sweep,
  toScreen,
} from "./geometry";
import {
  type Bounds,
  entityBounds,
  sceneBounds,
  intersects,
  viewBounds,
} from "./bounds";
type TextItem = { entity: Entity; color: string };
type Tile = {
  bounds: Bounds;
  strokes: Map<string, Path2D>;
  fills: Map<string, Path2D>;
  texts: TextItem[];
  points: TextItem[];
  highlight: Path2D;
};
export type Scene = { tiles: Tile[]; bounds: Bounds; elements: number };
/** Retain every entity. Native world-coordinate paths are cached in spatial tiles, never prefix-truncated. */
export function buildScene(
  entities: Entity[],
  layers: { name: string; color?: string }[],
  selected: string[],
): Scene {
  const bounds = sceneBounds(entities),
    size = Math.max(bounds[2] - bounds[0], bounds[3] - bounds[1], 1) / 24,
    tiles = new Map<string, Tile>(),
    colors = new Map(layers.map((l) => [l.name, l.color ?? "#ffffff"])),
    chosen = new Set(selected);
  let elements = 0;
  function visit(
    e: Entity,
    inheritedLayer = "0",
    inheritedColor = "#ffffff",
    highlight = false,
  ) {
    const layer = e.layer === "0" ? inheritedLayer : e.layer;
    const color =
      e.color ??
      (e.colorIndex === 0 ? inheritedColor : (colors.get(layer) ?? "#74dbe8"));
    if (e.segments) {
      for (const child of e.segments) visit(child, layer, color, highlight);
      return;
    }
    const box = entityBounds(e);
    if (!Number.isFinite(box[0])) return;
    elements++;
    const key =
      Math.floor(((box[0] + box[2]) / 2 - bounds[0]) / size) +
      "," +
      Math.floor(((box[1] + box[3]) / 2 - bounds[1]) / size);
    let tile = tiles.get(key);
    if (!tile) {
      tile = {
        bounds: [...box],
        strokes: new Map(),
        fills: new Map(),
        texts: [],
        points: [],
        highlight: new Path2D(),
      };
      tiles.set(key, tile);
    }
    tile.bounds = [
      Math.min(tile.bounds[0], box[0]),
      Math.min(tile.bounds[1], box[1]),
      Math.max(tile.bounds[2], box[2]),
      Math.max(tile.bounds[3], box[3]),
    ];
    if (e.type === "TEXT" || e.type === "MTEXT") {
      tile.texts.push({ entity: e, color: highlight ? "#ffcb6b" : color });
      return;
    }
    if (e.type === "POINT") {
      tile.points.push({ entity: e, color: highlight ? "#ffcb6b" : color });
      return;
    }
    const map = e.filled ? tile.fills : tile.strokes;
    let path = highlight ? tile.highlight : map.get(color);
    if (!path) {
      path = new Path2D();
      map.set(color, path);
    }
    if (e.type === "CIRCLE") {
      path.moveTo(e.c![0] + e.r!, e.c![1]);
      path.arc(e.c![0], e.c![1], e.r!, 0, Math.PI * 2);
    } else if (e.type === "ARC") {
      const [a, b] = sweep(e);
      path.moveTo(e.c![0] + e.r! * Math.cos(a), e.c![1] + e.r! * Math.sin(a));
      path.arc(e.c![0], e.c![1], e.r!, a, b);
    } else {
      const ps = e.pts ?? (e.a && e.b ? [e.a, e.b] : []);
      if (ps.length) {
        path.moveTo(...ps[0]);
        for (let i = 1; i < ps.length; i++) path.lineTo(...ps[i]);
        if (e.filled || e.closed) path.closePath();
      }
    }
  }
  for (const e of entities) visit(e, "0", "#ffffff", chosen.has(e.id));
  return { tiles: [...tiles.values()], bounds, elements };
}
export function paintScene(
  ctx: CanvasRenderingContext2D,
  scene: Scene,
  v: View,
  width: number,
  height: number,
  dpr: number,
): number {
  const viewport = viewBounds(v, width, height);
  let drawn = 0;
  ctx.setTransform(dpr * v.scale, 0, 0, -dpr * v.scale, dpr * v.x, dpr * v.y);
  ctx.lineWidth = 1.2 / v.scale;
  for (const tile of scene.tiles) {
    // The tile bounds include whole crossing entities, so culling cannot clip long lines or arcs.
    if (!intersects(tile.bounds, viewport)) continue;
    drawn++;
    for (const [color, path] of tile.fills) {
      ctx.fillStyle = color;
      ctx.fill(path);
    }
    for (const [color, path] of tile.strokes) {
      ctx.strokeStyle = color;
      ctx.stroke(path);
    }
    ctx.strokeStyle = "#ffcb6b";
    ctx.lineWidth = 2.5 / v.scale;
    ctx.stroke(tile.highlight);
    ctx.lineWidth = 1.2 / v.scale;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  for (const tile of scene.tiles) {
    if (!intersects(tile.bounds, viewport)) continue;
    for (const { entity: e, color } of tile.points) {
      if (!intersects(entityBounds(e), viewport)) continue;
      const p = toScreen(e.c!, v);
      ctx.fillStyle = color;
      ctx.fillRect(p[0], p[1], 1, 1);
    }
    for (const { entity: e, color } of tile.texts) {
      if (!intersects(entityBounds(e), viewport)) continue;
      const p = toScreen(e.c!, v),
        h = Math.max(0.25, (e.height ?? 1) * v.scale);
      ctx.save();
      ctx.translate(...p);
      ctx.rotate((-(e.rotation ?? 0) * Math.PI) / 180);
      ctx.scale(e.widthFactor ?? 1, 1);
      ctx.fillStyle = color;
      ctx.font = `${h}px sans-serif`;
      for (const [i, line] of (e.text ?? "").split("\n").entries())
        ctx.fillText(line, 0, i * h * 1.3);
      ctx.restore();
    }
  }
  return drawn;
}
