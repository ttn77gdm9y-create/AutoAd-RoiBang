import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { accountTablePagination, accountTableScroll } from "../src/pages/accountsPageLayout.ts";

test("keeps product account pagination visible with the left menu", () => {
  assert.deepEqual(accountTablePagination.position, ["bottomLeft"]);
  assert.equal(accountTablePagination.defaultPageSize, 100);
  assert.equal(accountTablePagination.showSizeChanger, true);
  assert.deepEqual(accountTablePagination.pageSizeOptions, ["20", "50", "100"]);
  assert.equal(accountTableScroll.x, 1420);
});

test("account bulk edit accepts pasted account ids as a target scope", () => {
  const source = readFileSync(new URL("../src/pages/AccountsPage.tsx", import.meta.url), "utf-8");

  assert.match(source, /bulkTargetMode/);
  assert.match(source, /bulkAdvertiserIdsText/);
  assert.match(source, /advertiser_ids_text/);
  assert.match(source, /粘贴账户 ID/);
});

test("account filters can search by product name and distinguish account source", () => {
  const source = readFileSync(new URL("../src/pages/AccountsPage.tsx", import.meta.url), "utf-8");

  assert.match(source, /product_query/);
  assert.match(source, /产品名 \/ 产品 Key/);
  assert.match(source, /source/);
  assert.match(source, /账户来源/);
  assert.match(source, /人工导入/);
  assert.match(source, /历史补全/);
  assert.match(source, /accountsPagination/);
  assert.match(source, /setAccountsPagination/);
});
