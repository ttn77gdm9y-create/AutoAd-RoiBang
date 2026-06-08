import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildGravityMaterialFlowState } from "../src/pages/gravityMaterialsFlow.ts";

test("asks the user to bind material source before syncing", () => {
  const state = buildGravityMaterialFlowState({
    bindingCount: 0,
    totalMaterials: 0,
    eligibleMaterials: 0,
    selectedMaterials: 0,
    selectedAccounts: 0,
    readinessStatus: "blocked",
    readinessNextAction: "绑定素材来源",
  });

  assert.equal(state.currentStep, 0);
  assert.equal(state.recommendation.title, "先绑定素材来源");
  assert.match(state.recommendation.description, /保存产品和目标专辑绑定/);
  assert.deepEqual(
    state.steps.map((step) => [step.title, step.status]),
    [
      ["绑定素材来源", "process"],
      ["更新引力素材", "wait"],
      ["本地素材库", "wait"],
      ["提前铺货预览", "wait"],
    ],
  );
});

test("asks the user to update gravity materials after binding but before local materials exist", () => {
  const state = buildGravityMaterialFlowState({
    bindingCount: 1,
    totalMaterials: 0,
    eligibleMaterials: 0,
    selectedMaterials: 0,
    selectedAccounts: 0,
    readinessStatus: "ready",
    readinessNextAction: "更新引力素材",
  });

  assert.equal(state.currentStep, 1);
  assert.equal(state.recommendation.title, "下一步更新引力素材");
  assert.match(state.recommendation.description, /不会下载素材文件/);
  assert.equal(state.steps[0].status, "finish");
  assert.equal(state.steps[1].status, "process");
});

test("asks the user to check available materials when local materials exist but none are eligible", () => {
  const state = buildGravityMaterialFlowState({
    bindingCount: 1,
    totalMaterials: 12,
    eligibleMaterials: 0,
    selectedMaterials: 0,
    selectedAccounts: 0,
    readinessStatus: "ready",
    readinessNextAction: "更新引力素材",
  });

  assert.equal(state.currentStep, 2);
  assert.equal(state.recommendation.title, "先检查素材为什么不可用");
  assert.match(state.recommendation.description, /缺 MD5|禁用|拒审/);
  assert.equal(state.steps[2].status, "process");
});

test("asks the user to generate preload preview after usable local materials exist", () => {
  const state = buildGravityMaterialFlowState({
    bindingCount: 1,
    totalMaterials: 20,
    eligibleMaterials: 6,
    selectedMaterials: 0,
    selectedAccounts: 0,
    readinessStatus: "ready",
    readinessNextAction: "更新引力素材",
  });

  assert.equal(state.currentStep, 3);
  assert.equal(state.recommendation.title, "可以生成提前铺货预览");
  assert.match(state.recommendation.description, /负责人为郭靖的启用账户/);
  assert.match(state.recommendation.description, /真实铺货前仍然必须输入“确认执行”/);
  assert.equal(state.steps[3].status, "process");
});

test("keeps the gravity material update prompt inside the gravity materials page", () => {
  const source = readFileSync(new URL("../src/pages/GravityMaterialsPage.tsx", import.meta.url), "utf-8");

  assert.doesNotMatch(source, /action=\{[\s\S]*?<Link to="\/workflow-center">[\s\S]*?去更新[\s\S]*?<\/Link>/);
  assert.match(source, /function startSyncFromMaterialList/);
  assert.match(source, /立即更新引力素材/);
  assert.match(source, /正在更新引力素材/);
});

test("renders numbered business sections and only shows usable local materials", () => {
  const source = readFileSync(new URL("../src/pages/GravityMaterialsPage.tsx", import.meta.url), "utf-8");

  assert.doesNotMatch(source, /statusFilter/);
  assert.doesNotMatch(source, /materialScopeOptions/);
  assert.doesNotMatch(source, /素材范围/);
  assert.doesNotMatch(source, /可用于后续/);
  assert.doesNotMatch(source, /有表现数据/);
  assert.match(source, /DEFAULT_TABLE_PAGE_SIZE/);
  assert.match(source, /TABLE_PAGE_SIZE_OPTIONS/);
  assert.match(source, /stepTitle\("1", "绑定素材来源"/);
  assert.match(source, /stepTitle\("2", gravityMaterialSyncCopy.title/);
  assert.match(source, /stepTitle\("3", "本地素材库"/);
  assert.match(source, /stepTitle\("4", "提前铺货到巨量账户"/);
});

test("offers automatic gravity material preloading before manual upload details", () => {
  const source = readFileSync(new URL("../src/pages/GravityMaterialsPage.tsx", import.meta.url), "utf-8");

  assert.match(source, /提前铺货到巨量账户/);
  assert.match(source, /生成提前铺货预览/);
  assert.match(source, /preloadPreview/);
  assert.match(source, /\/gravity-materials\/preload-preview/);
  assert.match(source, /负责人为郭靖的启用账户/);
  assert.match(source, /郭靖启用账户/);
  assert.match(source, /确认并铺货素材/);
});

test("auto-selects the first product so preload preview is not blocked by an empty product", () => {
  const source = readFileSync(new URL("../src/pages/GravityMaterialsPage.tsx", import.meta.url), "utf-8");

  assert.match(source, /const firstProduct = String\(productOptions\[0\]\?\.value/);
  assert.match(source, /selectProduct\(firstProduct\)/);
});
