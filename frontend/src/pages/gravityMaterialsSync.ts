export type GravityMaterialSyncRequestInput = {
  product: string;
  authFile: string;
  pageSize: string;
  maxPages: string;
};

export type GravityMaterialSyncWorkflowRequest = {
  product: string;
  auth_file: string;
  page_size: string;
  max_pages: string;
};

export const gravityMaterialSyncCopy = {
  title: "更新引力素材",
  description:
    "只读取引力素材的名称、归属专辑/文件夹、素材 ID、MD5、状态和表现数据，保存到 RoiBang 本地素材库；不会下载素材文件，不会上传到巨量账户，不影响每天从真实巨量账户同步来的素材数据。",
};

export function buildGravityMaterialSyncRequest(input: GravityMaterialSyncRequestInput): GravityMaterialSyncWorkflowRequest {
  return {
    product: input.product,
    auth_file: input.authFile || "data/gravity_token.json",
    page_size: input.pageSize || "100",
    max_pages: input.maxPages || "20",
  };
}
