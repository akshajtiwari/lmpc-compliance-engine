import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { readFile } from "node:fs/promises";

const WHITE_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAGAAAABAAQAAAADNT0+jAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAACYktHRAAB3YoTpAAAAAd0SU1FB+oJChI4JVqfD/MAAAAldEVYdGRhdGU6Y3JlYXRlADIwMjYtMDktMTBUMTg6NTY6MzcrMDA6MDDX5b2fAAAAJXRFWHRkYXRlOm1vZGlmeQAyMDI2LTA5LTEwVDE4OjU2OjM3KzAwOjAwprgFIwAAACh0RVh0ZGF0ZTp0aW1lc3RhbXAAMjAyNi0wOS0xMFQxODo1NjozNyswMDowMPGtJPwAAAAUSURBVCjPY/iPBBhGOaOcUQ4pHABsFf0ftgjPgQAAAABJRU5ErkJggg==",
  "base64",
);

test("login, inspect a listing, explain a rule, finalise and download", async ({ page }, testInfo) => {
  const email = process.env.LMPC_E2E_EMAIL;
  const password = process.env.LMPC_E2E_PASSWORD;
  expect(email, "LMPC_E2E_EMAIL must identify the bootstrap account").toBeTruthy();
  expect(password, "LMPC_E2E_PASSWORD must match its local password").toBeTruthy();

  await page.goto("/login");
  await expectWcag21Aa(page, testInfo, "login");
  await page.getByLabel("Email address").fill(email!);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Open workbench" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expectWcag21Aa(page, testInfo, "dashboard");

  await page.getByRole("link", { name: /Inspections/ }).click();
  await page.getByRole("link", { name: "New inspection" }).click();
  await page.getByRole("radio", { name: /E-commerce listing/ }).check();
  await page.getByLabel("Commodity category").selectOption("FOOD");
  await page.getByRole("textbox", { name: "Product-page URL (optional)", exact: true }).fill(
    "https://shop.example.test/products/e2e-packet",
  );
  await page.getByRole("textbox", { name: "Visible declaration text", exact: true }).fill(
    "MRP Rs. 45.00 (incl. of all taxes)\nNet Qty 500 g",
  );
  await page.locator("#listing-images").setInputFiles({
    name: "listing.png",
    mimeType: "image/png",
    buffer: WHITE_PNG,
  });
  await page.getByRole("button", { name: "Create and analyse" }).click();

  await expect(page).toHaveURL(/\/scans\/[0-9a-f-]+$/, { timeout: 120_000 });
  await expect(page.getByRole("heading", { name: "Listing source" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Open captured product page/ })).toHaveAttribute(
    "href", "https://shop.example.test/products/e2e-packet",
  );
  await expect(page.getByRole("heading", { name: "Rule findings" })).toBeVisible();
  await expectWcag21Aa(page, testInfo, "scan-detail");
  const listingDateRule = page.locator(".rule-card")
    .filter({ hasText: "not required in ECOMMERCE_LISTING (Rule 6(10))" }).first();
  await expect(listingDateRule).toContainText("NOT APPLICABLE");

  await page.locator(".info-button").first().click();
  await expect(page.getByRole("heading", { name: "What the requirement is" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What the system did" })).toBeVisible();
  await expectWcag21Aa(page, testInfo, "rule-explanation");
  await page.getByRole("button", { name: "Close" }).click();

  await page.getByRole("button", { name: "Finalise report" }).click();
  await expect(page.getByText(/Final report/).first()).toBeVisible({ timeout: 60_000 });
  const downloadStarted = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  const download = await downloadStarted;
  expect(download.suggestedFilename()).toMatch(/^LMPC-[0-9a-f]{8}\.pdf$/);
  const downloadPath = await download.path();
  expect(downloadPath).toBeTruthy();
  const pdf = await readFile(downloadPath!);
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
});

async function expectWcag21Aa(page: Page, testInfo: TestInfo, state: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  await testInfo.attach(`${state}-axe-results`, {
    body: Buffer.from(JSON.stringify({
      state,
      url: results.url,
      timestamp: results.timestamp,
      violations: results.violations,
      incomplete: results.incomplete,
    }, null, 2)),
    contentType: "application/json",
  });
  expect(results.violations, `${state} has WCAG 2.1 A/AA violations`).toEqual([]);
}
