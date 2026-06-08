import assert from "node:assert/strict";
import test from "node:test";

import { accountTablePagination, accountTableScroll } from "../src/pages/accountsPageLayout.ts";

test("keeps product account pagination visible with the left menu", () => {
  assert.deepEqual(accountTablePagination.position, ["bottomLeft"]);
  assert.equal(accountTablePagination.pageSize, 20);
  assert.equal(accountTablePagination.showSizeChanger, true);
  assert.equal(accountTableScroll.x, 1420);
});
