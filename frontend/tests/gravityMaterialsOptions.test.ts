import assert from "node:assert/strict";
import test from "node:test";

import { buildAlbumChoiceGroups } from "../src/pages/gravityMaterialsOptions.ts";

test("groups gravity album choices by target album and labels folders separately", () => {
  const groups = buildAlbumChoiceGroups([
    {
      "目标专辑": "黑旗-奇门（塔防）",
      "匹配状态": "已匹配",
      "匹配数量": 1,
      "可自动绑定": "是",
      "专辑/文件夹 ID": "365094",
      "名称": "黑旗-奇门（塔防）",
      "层级": 1,
      album_id: "365094",
      album_name: "黑旗-奇门（塔防）",
      "候选": [
        {
          "专辑/文件夹 ID": "365094",
          "名称": "黑旗-奇门（塔防）",
          "层级": 1,
          album_id: "365094",
          album_name: "黑旗-奇门（塔防）",
        },
        {
          "专辑/文件夹 ID": "365298",
          "名称": "基础素材",
          "层级": 2,
          album_id: "365094",
          album_name: "黑旗-奇门（塔防）",
          folder_id: "365298",
          folder_name: "基础素材",
        },
      ],
    },
  ]);

  assert.equal(groups.length, 1);
  assert.equal(groups[0].label, "黑旗-奇门（塔防）");
  assert.deepEqual(
    groups[0].options.map((option) => ({
      label: option.label,
      subLabel: option.subLabel,
      optionType: option.optionType,
    })),
    [
      {
        label: "绑定整个专辑",
        subLabel: "黑旗-奇门（塔防） · 专辑 ID 365094",
        optionType: "album",
      },
      {
        label: "只绑定文件夹：基础素材",
        subLabel: "所属专辑 黑旗-奇门（塔防） · 文件夹 ID 365298",
        optionType: "folder",
      },
    ],
  );
});
