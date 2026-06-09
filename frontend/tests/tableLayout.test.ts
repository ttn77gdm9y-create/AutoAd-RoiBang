import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

test("business table helper keeps headers sticky and horizontal scrolling inside the table", () => {
  const helperPath = new URL("../src/utils/tableLayout.ts", import.meta.url);

  assert.equal(existsSync(helperPath), true, "shared table layout helper should exist");
  const source = readFileSync(helperPath, "utf-8");
  assert.match(source, /businessTableClassName/);
  assert.match(source, /businessTableSticky[\s\S]*offsetHeader: 0/);
  assert.match(source, /businessTableScrollX[\s\S]*x: "max-content"/);
});

test("app layout fixes the sidebar and prevents page-level horizontal table scrolling", () => {
  const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf-8");

  assert.match(styles, /\.app-shell > \.ant-layout/);
  assert.match(styles, /\.app-content[\s\S]*?overflow-x: clip/);
  assert.match(styles, /@media \(min-width: 992px\)[\s\S]*?\.app-sider[\s\S]*?position: sticky/);
  assert.match(styles, /\.import-column\.full-width[\s\S]*?grid-column: 1 \/ -1/);
  assert.match(styles, /\.full-width > \.ant-space-item[\s\S]*?min-width: 0/);
  assert.match(styles, /\.business-table\.ant-table-wrapper[\s\S]*?max-width: 100%/);
  assert.doesNotMatch(styles, /\.business-table\.ant-table-wrapper[\s\S]*?overflow: hidden/);
  assert.match(styles, /\.business-table \.ant-table-pagination[\s\S]*?position: sticky[\s\S]*?left: 0/);
});

test("primary business pages opt into the shared business table behavior", () => {
  const pageFiles = [
    "../src/pages/AccountsPage.tsx",
    "../src/pages/GravityMaterialsPage.tsx",
    "../src/pages/SuggestionsPage.tsx",
    "../src/pages/TasksPage.tsx",
    "../src/pages/WorkflowCenterPage.tsx",
    "../src/pages/ProductAutomationPage.tsx",
    "../src/components/SummaryPanel.tsx",
  ];

  for (const pageFile of pageFiles) {
    const source = readFileSync(new URL(pageFile, import.meta.url), "utf-8");
    assert.match(source, /businessTableClassName/, `${pageFile} should use businessTableClassName`);
    assert.match(source, /businessTableSticky/, `${pageFile} should enable sticky table headers`);
  }
});
