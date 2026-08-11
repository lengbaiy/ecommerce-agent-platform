<script setup lang="ts">
import { computed } from "vue";

import type { NavigationItem } from "../config/navigation";

const props = defineProps<{ module: NavigationItem }>();

const moduleContent: Record<
  string,
  {
    action: string;
    prompt: string;
    metrics: { label: string; value: string; color: string }[];
    capabilities: { title: string; description: string; badge: string }[];
    steps: string[];
  }
> = {
  tasks: {
    action: "创建任务",
    prompt: "按目标、任务编号或负责人搜索，查看当前节点与错误恢复状态。",
    metrics: [
      { label: "运行中", value: "6", color: "info" },
      { label: "待审批", value: "2", color: "warning" },
      { label: "今日完成", value: "38", color: "success" },
    ],
    capabilities: [
      { title: "任务时间线", description: "查看计划、节点、Tool 调用与状态变化。", badge: "Trace" },
      { title: "断点恢复", description: "从可恢复节点继续，不重复副作用步骤。", badge: "Recover" },
      { title: "人工审批", description: "对正式保存与发布操作锁定参数快照。", badge: "HITL" },
    ],
    steps: ["创建", "规划", "执行", "审批 / 完成"],
  },
  market: {
    action: "评估市场机会",
    prompt: "分析便携咖啡机在 US 市场是否值得进入，目标毛利不低于 30%。",
    metrics: [
      { label: "监测类目", value: "18", color: "primary" },
      { label: "竞品样本", value: "1,286", color: "info" },
      { label: "机会评分", value: "78", color: "success" },
    ],
    capabilities: [
      {
        title: "类目扫描",
        description: "规模、增长、价格带和集中度形成市场快照。",
        badge: "Market",
      },
      {
        title: "竞品拆解",
        description: "对比价格、卖点、评价、排名和商品事实。",
        badge: "Competitor",
      },
      { title: "利润约束", description: "用确定性计算器验证毛利与进入门槛。", badge: "Profit" },
    ],
    steps: ["市场扫描", "竞品与评论", "利润测算", "机会评审"],
  },
  strategy: {
    action: "生成商品策略",
    prompt: "选择已完成的市场报告，生成用户定位、价格带、卖点与差异化方案。",
    metrics: [
      { label: "策略草案", value: "12", color: "primary" },
      { label: "证据覆盖", value: "96%", color: "success" },
      { label: "平均毛利", value: "34.2%", color: "info" },
    ],
    capabilities: [
      {
        title: "人群定位",
        description: "从评论与购买动机提炼目标用户和使用场景。",
        badge: "Audience",
      },
      { title: "价值主张", description: "把商品事实转化为可验证的核心卖点。", badge: "Value" },
      { title: "风险清单", description: "暴露成本、合规、供应链与竞争风险。", badge: "Risk" },
    ],
    steps: ["加载证据", "定位与定价", "差异化设计", "策略评审"],
  },
  listing: {
    action: "新建 Listing",
    prompt: "选择 SKU、站点与平台模板，生成并校验结构化 Listing。",
    metrics: [
      { label: "本周生成", value: "46", color: "primary" },
      { label: "规则通过率", value: "97.8%", color: "success" },
      { label: "待发布", value: "5", color: "warning" },
    ],
    capabilities: [
      {
        title: "结构化生成",
        description: "Title、Bullet、Description 与 Search Terms。",
        badge: "Schema",
      },
      { title: "事实核验", description: "禁止生成商品资料中不存在的参数与功效。", badge: "Facts" },
      { title: "平台合规", description: "检查长度、禁用词、类目规则与品牌口径。", badge: "Policy" },
    ],
    steps: ["读取商品事实", "生成文案", "规则校验", "审批发布"],
  },
  diagnosis: {
    action: "开始经营诊断",
    prompt: "为什么本周转化率下降？请按 SKU、流量来源和时间窗口诊断。",
    metrics: [
      { label: "活跃预警", value: "12", color: "danger" },
      { label: "已证实归因", value: "8", color: "success" },
      { label: "平均响应", value: "42s", color: "info" },
    ],
    capabilities: [
      {
        title: "指标异常",
        description: "程序化计算环比、同比、阈值和数据质量。",
        badge: "Metrics",
      },
      { title: "归因假设", description: "区分已证实、高可能与待验证原因。", badge: "Cause" },
      { title: "动作建议", description: "按影响、成本与风险排序建议动作。", badge: "Action" },
    ],
    steps: ["加载指标", "异常检测", "归因解释", "动作排序"],
  },
  knowledge: {
    action: "检索知识库",
    prompt: "检索商品事实、平台政策、品牌规范或运营 SOP，并查看原始引用。",
    metrics: [
      { label: "有效文档", value: "2,418", color: "primary" },
      { label: "引用命中率", value: "95.6%", color: "success" },
      { label: "即将过期", value: "7", color: "warning" },
    ],
    capabilities: [
      {
        title: "版本资产",
        description: "来源、类型、生效时间和租户元数据完整。",
        badge: "Version",
      },
      { title: "混合检索", description: "关键词与向量召回后统一重排。", badge: "Hybrid" },
      { title: "引用回看", description: "从结论回到 Chunk、文档和原始来源。", badge: "Citation" },
    ],
    steps: ["文档解析", "切分入库", "混合召回", "重排引用"],
  },
  evaluation: {
    action: "运行评测",
    prompt: "选择评测集或 Trace，查看路由、Tool、证据和任务完成质量。",
    metrics: [
      { label: "任务完成率", value: "92.4%", color: "success" },
      { label: "证据覆盖率", value: "96.1%", color: "primary" },
      { label: "关键幻觉率", value: "1.3%", color: "warning" },
    ],
    capabilities: [
      {
        title: "全链 Trace",
        description: "按任务查看 Agent、模型、Tool 与审批记录。",
        badge: "Trace",
      },
      { title: "固定评测集", description: "模型、Prompt、Tool 变更后自动回归。", badge: "Eval" },
      {
        title: "故障恢复",
        description: "注入超时、非法输出和空召回验证恢复策略。",
        badge: "Chaos",
      },
    ],
    steps: ["选择数据集", "执行用例", "规则 + Judge", "生成报告"],
  },
};

const content = computed(() => moduleContent[props.module.id] ?? moduleContent.tasks);
</script>

<template>
  <CRow class="align-items-center mb-4">
    <CCol :md="8">
      <div class="text-body-secondary small mb-1">{{ module.apiModule }}</div>
      <h2 class="mb-1">{{ module.label }}</h2>
      <div class="text-body-secondary">{{ module.description }}</div>
    </CCol>
    <CCol :md="4" class="text-md-end mt-3 mt-md-0">
      <CBadge color="success" class="me-2">服务正常</CBadge
      ><CButton color="primary">{{ content.action }}</CButton>
    </CCol>
  </CRow>

  <CCard class="mb-4 border-primary">
    <CCardBody class="d-flex align-items-center gap-3 flex-wrap">
      <div class="agent-icon"><CIcon icon="cil-lightbulb" size="xl" /></div>
      <div class="flex-grow-1">
        <div class="fw-semibold">告诉 Agent 你想完成什么</div>
        <div class="small text-body-secondary mt-1">{{ content.prompt }}</div>
      </div>
      <CButton color="primary">
        {{ content.action }}<CIcon icon="cil-arrow-right" class="ms-2" />
      </CButton>
    </CCardBody>
  </CCard>

  <CRow :xs="{ gutter: 4 }" class="mb-4">
    <CCol v-for="metric in content.metrics" :key="metric.label" :md="4">
      <CWidgetStatsB
        class="mb-3"
        :color="metric.color"
        inverse
        :value="metric.value"
        :title="metric.label"
      >
        <template #progress><CProgress white :value="72" /></template>
      </CWidgetStatsB>
    </CCol>
  </CRow>

  <CRow>
    <CCol :lg="8">
      <CCard class="mb-4">
        <CCardHeader>核心能力</CCardHeader
        ><CCardBody>
          <CRow :xs="{ gutter: 4 }">
            <CCol v-for="(item, index) in content.capabilities" :key="item.title" :md="4">
              <CCard class="h-100">
                <CCardBody>
                  <div class="d-flex justify-content-between align-items-center mb-3">
                    <span class="text-body-secondary">0{{ index + 1 }}</span
                    ><CBadge color="primary" shape="rounded-pill">{{ item.badge }}</CBadge>
                  </div>
                  <h5>{{ item.title }}</h5>
                  <p class="small text-body-secondary mb-0">{{ item.description }}</p>
                </CCardBody>
              </CCard>
            </CCol>
          </CRow>
        </CCardBody>
      </CCard>
    </CCol>
    <CCol :lg="4">
      <CCard class="mb-4">
        <CCardHeader>标准执行链路</CCardHeader
        ><CListGroup flush numbered>
          <CListGroupItem
            v-for="step in content.steps"
            :key="step"
            class="d-flex justify-content-between align-items-center"
          >
            {{ step }}<CIcon icon="cil-check-circle" class="text-success" />
          </CListGroupItem>
        </CListGroup>
      </CCard>
    </CCol>
  </CRow>
</template>

<style scoped>
.agent-icon {
  display: grid;
  width: 48px;
  height: 48px;
  flex: 0 0 auto;
  color: var(--cui-primary);
  background: var(--cui-primary-bg-subtle);
  border-radius: var(--cui-border-radius-lg);
  place-items: center;
}
</style>
