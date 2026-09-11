// Pure geometry for the scale-reference marking screen (plan §6.3). The phone
// only measures where the officer dragged corner handles; every legal conclusion
// is re-derived server-side from the pinned ISO ID-1 card dimensions.
import type {PanelLabel} from "./types";

export type Point = {x: number; y: number};

export const ID1_ASPECT = 85.6 / 53.98;

// The server re-checks everything; this pre-gate only exists so the officer can
// fix a clearly mis-marked quad before uploading.
export const CARD_ASPECT_TOLERANCE = 0.22;

export function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function crossProduct(a: Point, b: Point): number {
  return a.x * b.y - a.y * b.x;
}

export function quadConvex(points: Point[]): boolean {
  if (points.length !== 4) return false;
  const signs: boolean[] = [];
  for (let index = 0; index < 4; index++) {
    const start = points[index];
    const middle = points[(index + 1) % 4];
    const end = points[(index + 2) % 4];
    const turn = crossProduct(
      {x: middle.x - start.x, y: middle.y - start.y},
      {x: end.x - middle.x, y: end.y - middle.y},
    );
    if (Math.abs(turn) < 1e-6) return false;
    signs.push(turn > 0);
  }
  return signs.every(Boolean) || signs.every((value) => !value);
}

export function quadAspect(points: Point[]): number {
  const longEdge = (distance(points[0], points[1]) + distance(points[2], points[3])) / 2;
  const shortEdge = (distance(points[1], points[2]) + distance(points[3], points[0])) / 2;
  if (shortEdge <= 0) return Infinity;
  return longEdge / shortEdge;
}

// Advisory only: the same bound the server enforces, shown early.
export function cardMarksPlausible(points: Point[]): boolean {
  if (!quadConvex(points)) return false;
  return Math.abs(quadAspect(points) - ID1_ASPECT) / ID1_ASPECT <= CARD_ASPECT_TOLERANCE;
}

// Handle positions live in displayed-view coordinates; the server needs original
// image pixel coordinates so the marks survive resizing and thumbnails.
export function toImagePoints(
  points: Point[], viewWidth: number, viewHeight: number,
  imageWidth: number, imageHeight: number,
): number[][] {
  if (viewWidth <= 0 || viewHeight <= 0 || imageWidth <= 0 || imageHeight <= 0) {
    throw new Error("Cannot map marks without view and image dimensions");
  }
  return points.map((point) => [
    Math.round(Math.min(Math.max(point.x / viewWidth, 0), 1) * imageWidth * 1000) / 1000,
    Math.round(Math.min(Math.max(point.y / viewHeight, 0), 1) * imageHeight * 1000) / 1000,
  ]);
}

// Listing screenshots keep their own panel labels: LISTING, then LISTING_2..6.
export function listingPanels(count: number): PanelLabel[] {
  if (count < 1 || count > 6) throw new Error("A listing carries 1-6 screenshots");
  const labels: PanelLabel[] = ["LISTING"];
  for (let number = 2; number <= count; number++) {
    labels.push(`LISTING_${number}` as PanelLabel);
  }
  return labels;
}