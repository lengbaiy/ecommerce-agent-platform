export type NavigationItem = {
  id: string;
  label: string;
  shortLabel: string;
  icon: string;
  description: string;
  apiModule: string;
  group: "overview" | "agent" | "system";
};

export const navigationItems: NavigationItem[] = [
  {
    id: "dashboard",
    label: "经营总览",
    shortLabel: "总览",
    icon: "⌂",
    description: "GMV、订单、转化与库存风险",
    apiModule: "dashboard",
    group: "overview",
  },
  {
    id: "tasks",
    label: "Agent 任务",
    shortLabel: "任务",
    icon: "◎",
    description: "状态、节点、Trace、审批与恢复",
    apiModule: "task_center",
    group: "overview",
  },
  {
    id: "market",
    label: "市场机会",
    shortLabel: "市场",
    icon: "↗",
    description: "市场、竞品、评论与利润证据",
    apiModule: "market_intelligence",
    group: "agent",
  },
  {
    id: "strategy",
    label: "商品策略",
    shortLabel: "策略",
    icon: "◇",
    description: "定位、价格、卖点、差异化与风险",
    apiModule: "product_strategy",
    group: "agent",
  },
  {
    id: "listing",
    label: "Listing 工坊",
    shortLabel: "Listing",
    icon: "✦",
    description: "结构化生成、事实与平台规则校验",
    apiModule: "listing",
    group: "agent",
  },
  {
    id: "diagnosis",
    label: "经营诊断",
    shortLabel: "诊断",
    icon: "⌁",
    description: "销售、流量、转化与库存归因",
    apiModule: "operations_diagnosis",
    group: "agent",
  },
  {
    id: "knowledge",
    label: "知识资产",
    shortLabel: "知识库",
    icon: "▤",
    description: "商品事实、平台规则与运营 SOP",
    apiModule: "knowledge_base",
    group: "system",
  },
  {
    id: "evaluation",
    label: "评测与追踪",
    shortLabel: "评测",
    icon: "✓",
    description: "Trace、恢复与质量评测",
    apiModule: "evaluation",
    group: "system",
  },
  {
    id: "permissions",
    label: "权限管理",
    shortLabel: "权限",
    icon: "shield",
    description: "企业用户、角色与服务端权限映射",
    apiModule: "identity_access",
    group: "system",
  },
];
