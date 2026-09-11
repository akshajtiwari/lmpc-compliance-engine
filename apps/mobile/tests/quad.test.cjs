const test = require("node:test");
const assert = require("node:assert/strict");

const {cardMarksPlausible, distance, listingPanels, quadAspect, quadConvex,
  toImagePoints} = require("../.test-dist/quad.js");

function quad(points) { return points.map(([x, y]) => ({x, y})); }

test("a face-on card quad is convex and plausible", () => {
  const marks = quad([[60, 40], [1000, 40], [1000, 680], [60, 680]]);
  assert.ok(quadConvex(marks));
  assert.ok(cardMarksPlausible(marks));
});

test("a 30-degree foreshortened card still passes the advisory gate", () => {
  const cos30 = Math.cos(Math.PI / 6);
  const marks = quad([[60, 40], [60 + 940 * cos30, 40], [60 + 940 * cos30, 680], [60, 680]]);
  assert.ok(cardMarksPlausible(marks));
});

test("a square is not a credit card", () => {
  assert.equal(cardMarksPlausible(quad([[60, 40], [400, 40], [400, 380], [60, 380]])), false);
});

test("bowties and collinear marks are rejected", () => {
  assert.equal(quadConvex(quad([[60, 40], [400, 380], [400, 40], [60, 380]])), false);
  assert.equal(quadConvex(quad([[60, 40], [400, 40], [60, 40], [400, 40]])), false);
});

test("distance is the plain euclidean length", () => {
  assert.equal(distance({x: 0, y: 0}, {x: 3, y: 4}), 5);
});

test("view marks map into original image pixels", () => {
  const marks = quad([[0, 0], [200, 0], [200, 300], [0, 300]]);
  const mapped = toImagePoints(marks, 200, 300, 4000, 6000);
  assert.deepEqual(mapped, [[0, 0], [4000, 0], [4000, 6000], [0, 6000]]);
});

test("marks cannot escape the image bounds", () => {
  const mapped = toImagePoints(quad([[-40, -10], [210, 0], [210, 320], [0, 320]]),
    200, 300, 1000, 1500);
  assert.deepEqual(mapped[0], [0, 0]);
  assert.equal(mapped[1][0], 1000);
  assert.equal(mapped[2][1], 1500);
});

test("listing screenshots take sequential panel labels", () => {
  assert.deepEqual(listingPanels(1), ["LISTING"]);
  assert.deepEqual(listingPanels(3), ["LISTING", "LISTING_2", "LISTING_3"]);
  assert.throws(() => listingPanels(0));
  assert.throws(() => listingPanels(7));
});