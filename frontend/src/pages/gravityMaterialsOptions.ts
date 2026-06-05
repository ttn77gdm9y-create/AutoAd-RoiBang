export type AlbumNode = {
  "专辑/文件夹 ID": string;
  "名称": string;
  "层级": number;
  album_id?: string;
  album_name?: string;
  folder_id?: string;
  folder_name?: string;
};

export type TargetAlbumRow = AlbumNode & {
  "目标专辑": string;
  "匹配状态": string;
  "匹配数量": number;
  "可自动绑定": string;
  "候选"?: AlbumNode[];
};

export type AlbumChoiceOption = {
  value: string;
  label: string;
  subLabel: string;
  searchText: string;
  optionType: "album" | "folder";
  album_id: string;
  album_name: string;
  folder_id: string;
  folder_name: string;
};

export type AlbumChoiceGroup = {
  label: string;
  targetAlbum: string;
  options: AlbumChoiceOption[];
};

export function buildAlbumChoiceGroups(targetAlbums: TargetAlbumRow[]): AlbumChoiceGroup[] {
  return targetAlbums.map((target) => {
    const targetAlbum = String(target["目标专辑"] || target.album_name || target["名称"] || "").trim();
    const rawNodes = Array.isArray(target["候选"]) ? [...target["候选"]] : [];
    const hasAlbumNode = rawNodes.some((node) => !String(node.folder_id ?? "").trim() && Number(node["层级"] ?? 1) <= 1);

    if (!hasAlbumNode) {
      rawNodes.unshift(target);
    }

    const seen = new Set<string>();
    const options = rawNodes
      .map((node) => buildAlbumChoiceOption(node, targetAlbum))
      .filter((option): option is AlbumChoiceOption => {
        if (!option || seen.has(option.value)) {
          return false;
        }
        seen.add(option.value);
        return true;
      })
      .sort((left, right) => {
        if (left.optionType === right.optionType) {
          return 0;
        }
        return left.optionType === "album" ? -1 : 1;
      });

    return {
      label: targetAlbum,
      targetAlbum,
      options,
    };
  });
}

export function flattenAlbumChoiceGroups(groups: AlbumChoiceGroup[]): AlbumChoiceOption[] {
  return groups.flatMap((group) => group.options);
}

function buildAlbumChoiceOption(node: AlbumNode, targetAlbum: string): AlbumChoiceOption | null {
  const nodeId = String(node["专辑/文件夹 ID"] ?? "").trim();
  const level = Number(node["层级"] ?? 1);
  const nodeName = String(node["名称"] ?? "").trim();
  const folderId = String(node.folder_id ?? (level > 1 ? nodeId : "")).trim();
  const folderName = String(node.folder_name ?? (folderId ? nodeName : "")).trim();
  const albumId = String(node.album_id ?? (folderId ? "" : nodeId)).trim();
  const albumName = String(node.album_name ?? (folderId ? targetAlbum : nodeName || targetAlbum)).trim();

  if (!albumId && !folderId) {
    return null;
  }

  if (folderId) {
    const label = `只绑定文件夹：${folderName || nodeName || folderId}`;
    const subLabel = `所属专辑 ${albumName || targetAlbum} · 文件夹 ID ${folderId}`;
    return {
      value: `folder:${albumId}:${folderId}`,
      label,
      subLabel,
      searchText: `${targetAlbum} ${label} ${subLabel}`,
      optionType: "folder",
      album_id: albumId,
      album_name: albumName || targetAlbum,
      folder_id: folderId,
      folder_name: folderName || nodeName,
    };
  }

  const label = "绑定整个专辑";
  const subLabel = `${albumName || targetAlbum} · 专辑 ID ${albumId}`;
  return {
    value: `album:${albumId}`,
    label,
    subLabel,
    searchText: `${targetAlbum} ${label} ${subLabel}`,
    optionType: "album",
    album_id: albumId,
    album_name: albumName || targetAlbum,
    folder_id: "",
    folder_name: "",
  };
}
