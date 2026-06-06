import assert from "node:assert/strict";
import test from "node:test";

import { buildGravityMaterialSyncRequest, gravityMaterialSyncCopy } from "../src/pages/gravityMaterialsSync.ts";

test("builds a fixed gravity material metadata sync workflow request", () => {
  assert.deepEqual(
    buildGravityMaterialSyncRequest({
      product: "点点英雄",
      authFile: "data/gravity_token.json",
      pageSize: "100",
      maxPages: "20",
    }),
    {
      product: "点点英雄",
      auth_file: "data/gravity_token.json",
      page_size: "100",
      max_pages: "20",
    },
  );
});

test("explains gravity sync as metadata only without touching account material sync", () => {
  assert.equal(gravityMaterialSyncCopy.title, "同步引力素材资料到本地");
  assert.match(gravityMaterialSyncCopy.description, /不会下载素材文件/);
  assert.match(gravityMaterialSyncCopy.description, /不影响每天从真实巨量账户同步来的素材数据/);
});
