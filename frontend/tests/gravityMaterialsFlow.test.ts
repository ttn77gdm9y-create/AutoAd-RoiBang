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
      ["查看并选择素材", "wait"],
      ["生成推送预览", "wait"],
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

test("asks the user to generate push preview only after materials and accounts are selected", () => {
  const state = buildGravityMaterialFlowState({
    bindingCount: 1,
    totalMaterials: 20,
    eligibleMaterials: 6,
    selectedMaterials: 2,
    selectedAccounts: 1,
    readinessStatus: "ready",
    readinessNextAction: "更新引力素材",
  });

  assert.equal(state.currentStep, 3);
  assert.equal(state.recommendation.title, "可以生成推送预览");
  assert.match(state.recommendation.description, /真实推送前仍然必须输入“确认执行”/);
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
  assert.match(source, /stepTitle\("4", "推送引力素材到巨量账户"/);
});
