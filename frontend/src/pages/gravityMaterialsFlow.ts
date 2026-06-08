export type GravityFlowStepStatus = "wait" | "process" | "finish" | "error";

export type GravityFlowInput = {
  bindingCount: number;
  totalMaterials: number;
  eligibleMaterials: number;
  selectedMaterials: number;
  selectedAccounts: number;
  readinessStatus?: string;
  readinessNextAction?: string;
};

export type GravityFlowState = {
  currentStep: number;
  recommendation: {
    title: string;
    description: string;
    type: "info" | "success" | "warning" | "error";
  };
  steps: Array<{
    title: string;
    description: string;
    status: GravityFlowStepStatus;
  }>;
};

export function buildGravityMaterialFlowState(input: GravityFlowInput): GravityFlowState {
  const bindingCount = Math.max(0, Number(input.bindingCount || 0));
  const totalMaterials = Math.max(0, Number(input.totalMaterials || 0));
  const eligibleMaterials = Math.max(0, Number(input.eligibleMaterials || 0));
  const blockedByToken = input.readinessStatus === "blocked" && input.readinessNextAction === "检查引力 Token";

  if (bindingCount <= 0) {
    return flowState(0, ["process", "wait", "wait", "wait"], {
      title: "先绑定素材来源",
      description: "先保存产品和目标专辑绑定，系统才知道应该从哪些引力专辑更新素材。",
      type: "info",
    });
  }

  if (blockedByToken) {
    return flowState(1, ["finish", "error", "wait", "wait"], {
      title: "先检查引力 Token",
      description: "当前更新被 Token 文件阻塞。请先确认 Token 文件存在且字段完整，然后再更新引力素材。",
      type: "warning",
    });
  }

  if (totalMaterials <= 0) {
    return flowState(1, ["finish", "process", "wait", "wait"], {
      title: "下一步更新引力素材",
      description: "本地还没有引力素材资料。点击“生成更新预览”，再启动更新；这一步不会下载素材文件，不会上传到巨量账户。",
      type: "info",
    });
  }

  if (eligibleMaterials <= 0) {
    return flowState(2, ["finish", "finish", "process", "wait"], {
      title: "先检查素材为什么不可用",
      description: "本地已有素材，但暂时没有可铺货素材。重点看缺 MD5、禁用、拒审等不可用原因。",
      type: "warning",
    });
  }

  return flowState(3, ["finish", "finish", "finish", "process"], {
    title: "可以生成提前铺货预览",
    description: "系统会自动使用产品账户库里负责人为郭靖的启用账户和本地可铺货素材生成预览；真实铺货前仍然必须输入“确认执行”。",
    type: "warning",
  });
}

function flowState(
  currentStep: number,
  statuses: GravityFlowStepStatus[],
  recommendation: GravityFlowState["recommendation"],
): GravityFlowState {
  const titles = ["绑定素材来源", "更新引力素材", "本地素材库", "提前铺货预览"];
  const descriptions = ["选产品和引力专辑", "只读取资料，不下载文件", "只展示可铺货素材", "真实动作前复核"];
  return {
    currentStep,
    recommendation,
    steps: titles.map((title, index) => ({
      title,
      description: descriptions[index],
      status: statuses[index],
    })),
  };
}
