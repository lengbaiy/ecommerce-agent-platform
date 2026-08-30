<script setup lang="ts">
import { computed } from "vue";

import type {
  AgentTask,
  MarketIntelligenceReport,
  TaskEvent,
  TaskEventType,
  TaskStatus,
} from "../types/marketIntelligence";

const props = defineProps<{
  task: AgentTask;
  report: MarketIntelligenceReport | null;
  events: TaskEvent[];
  streaming: boolean;
  cancelling: boolean;
}>();
const emit = defineEmits<{ cancel: [] }>();

const terminal = new Set<TaskStatus>(["COMPLETED", "DEGRADED", "FAILED", "CANCELLED"]);
const statusCopy: Record<TaskStatus, string> = {
  PENDING: "等待 Worker",
  PLANNING: "正在规划",
  RUNNING: "分析进行中",
  WAITING_APPROVAL: "等待确认",
  RETRYING: "正在重试",
  DEGRADED: "降级完成",
  COMPLETED: "分析完成",
  FAILED: "执行失败",
  CANCELLED: "已取消",
};
const eventCopy: Partial<Record<TaskEventType, string>> = {
  "task.planning": "任务规划",
  "task.running": "开始执行",
  "task.waiting_approval": "等待确认",
  "task.degraded": "降级完成",
  "task.completed": "任务完成",
  "task.failed": "任务失败",
  "task.cancel_requested": "正在取消",
  "task.cancelled": "任务取消",
  "node.started": "节点开始",
  "node.completed": "节点完成",
  "node.retrying": "节点重试",
  "tool.started": "工具调用",
  "tool.progress": "批次进度",
  "tool.completed": "工具完成",
  "tool.failed": "工具异常",
};
const stepCopy: Record<string, string> = {
  validate_input: "检查分析条件",
  search_products: "读取商品样本",
  build_competitor_matrix: "整理竞品信息",
  build_market_snapshot: "计算市场指标",
  analyze_reviews: "分析用户评论",
  calculate_profit: "测算利润空间",
  synthesize_report: "生成市场报告",
  validate_evidence: "核对报告证据",
  persist_result: "保存分析结果",
  planning: "准备分析任务",
  completed: "完成市场分析",
  degraded: "完成市场分析",
  failed: "分析任务已停止",
  cancelled: "分析任务已取消",
};
const errorCopy: Record<string, { title: string; reason: string; action: string }> = {
  DATA_EMPTY: {
    title: "没有获取到可用商品数据",
    reason: "匹配的数据集没有返回符合分析要求的商品，本次分析无法继续。",
    action: "请确认 Worker 已加载最新数据集，并检查商品标题、价格和商品编号等必填数据。",
  },
  DATASET_NOT_AVAILABLE: {
    title: "没有匹配到可用数据集",
    reason: "当前商品、市场、平台或关键词没有对应的数据集。",
    action: "请返回确认参数，检查商品类目和关键词是否与数据集 manifest 一致。",
  },
  UNSUPPORTED_DATA_SOURCE: {
    title: "当前数据来源尚未接入",
    reason: "执行服务没有找到支持该平台和数据模式的数据适配器。",
    action: "请联系技术人员检查 Worker 的 Adapter 注册和运行配置。",
  },
  COLLECTION_INTERNAL_ERROR: {
    title: "商品数据读取或保存失败",
    reason: "数据采集过程中发生内部异常，已经停止当前步骤。",
    action: "请稍后重新执行；如果仍然失败，请将任务编号交给技术人员排查。",
  },
  LLM_TIMEOUT: {
    title: "智能分析服务响应超时",
    reason: "模型在规定时间内没有完成当前分析。",
    action: "可以稍后重新执行；多次超时时请联系技术人员检查模型服务。",
  },
  LLM_UNAVAILABLE: {
    title: "智能分析服务暂时不可用",
    reason: "模型服务当前无法完成请求。",
    action: "请稍后重新执行，或查看是否已经生成可用的降级报告。",
  },
  SCHEMA_VALIDATION_FAILED: {
    title: "数据格式不符合分析要求",
    reason: "输入数据或模型结果缺少必要字段，系统无法安全继续。",
    action: "请将任务编号交给技术人员，检查数据集或模型输出格式。",
  },
};
const degradedReasonCopy: Record<string, string> = {
  LLM_UNAVAILABLE: "报告合成服务不可用",
  COST_INPUT_UNAVAILABLE: "利润参数不完整",
  DATA_CONFLICT: "关键数据存在冲突",
  PRODUCT_COLLECTION_PARTIAL: "商品样本不完整",
  REVIEW_DATA_INCOMPLETE: "评论分析覆盖有限",
  MARKET_METRIC_INCOMPLETE: "市场指标不完整",
  BRAND_DATA_UNAVAILABLE: "品牌数据不足",
};
const degradedReasonPriority = Object.keys(degradedReasonCopy);

const degradedReason = computed(() => {
  if (props.task.status !== "DEGRADED") return "";
  const limitations = props.report?.data_limitations || [];
  const reasons = new Map<string, string>(
    limitations.map<[string, string]>((item) => [
      item.reason_code,
      degradedReasonCopy[item.reason_code] || item.message,
    ]),
  );
  const ordered = [
    ...degradedReasonPriority.filter((code) => reasons.has(code)),
    ...[...reasons.keys()].filter((code) => !degradedReasonPriority.includes(code)),
  ].map((code) => reasons.get(code) as string);
  if (!ordered.length) return "存在数据限制";
  const visible = ordered.slice(0, 3).join("、");
  return ordered.length > 3 ? `${visible}等` : visible;
});
const currentStage = computed(() => stepLabel(props.task.current_step));
const completedSteps = computed(
  () => props.events.filter(
    (event) =>
      event.event_type === "node.completed" &&
      event.status !== "FAILED" &&
      !event.summary.includes(" stopped with "),
  ).length,
);
const errorDetails = computed(() =>
  props.task.error && Object.keys(props.task.error.details).length
    ? JSON.stringify(props.task.error.details, null, 2)
    : "",
);
const taskError = computed(() => {
  if (!props.task.error) return null;
  return errorCopy[props.task.error.code] || {
    title: "任务执行过程中遇到问题",
    reason: "系统未能完成当前分析步骤。",
    action: "请稍后重新执行；如果问题持续出现，请将任务编号交给技术人员。",
  };
});

const progress = computed(() => {
  if (props.task.status === "PENDING") return 8;
  if (props.task.status === "PLANNING") return 18;
  if (props.task.status === "RUNNING" || props.task.status === "RETRYING") {
    return Math.min(82, 28 + props.events.filter((event) => event.event_type.endsWith("completed")).length * 8);
  }
  if (props.task.status === "WAITING_APPROVAL") return 90;
  return 100;
});
const visibleEvents = computed(() => [...props.events].reverse().slice(0, 14));
const canCancel = computed(() => !terminal.has(props.task.status));

function stepLabel(step: string | null) {
  if (!step) return "正在等待下一步";
  return stepCopy[step] || "处理分析数据";
}

function eventTone(event: TaskEvent) {
  if (event.status === "FAILED" || event.summary.includes(" stopped with ") || event.event_type.includes("failed") || event.event_type.includes("cancel")) return "danger";
  if (event.event_type.includes("retry") || event.event_type.includes("degraded")) return "warning";
  if (event.event_type.endsWith("completed")) return "success";
  return "active";
}

function eventTitle(event: TaskEvent) {
  const stage = stepLabel(event.step);
  if (event.event_type === "node.started") return `${stage}开始`;
  if (event.event_type === "node.completed") {
    return event.status === "FAILED" || event.summary.includes(" stopped with ")
      ? `${stage}未完成`
      : `${stage}完成`;
  }
  if (event.event_type === "node.retrying") return `${stage}正在重试`;
  if (event.event_type === "tool.started") return `${stage}正在处理`;
  if (event.event_type === "tool.completed") return `${stage}处理完成`;
  if (event.event_type === "tool.failed") return `${stage}处理异常`;
  if (event.event_type === "tool.progress") return `${stage}进度更新`;
  return eventCopy[event.event_type] || "任务状态更新";
}

function eventDescription(event: TaskEvent) {
  const stopped = event.summary.match(/stopped with ([A-Z0-9_]+)/);
  if (stopped) return errorCopy[stopped[1]]?.reason || "该步骤遇到问题，任务已经停止。";
  const batch = event.summary.match(
    /completed LLM batch (\d+)\/(\d+); analyzed (\d+)\/(\d+) selected reviews from (\d+) collected reviews/i,
  );
  if (batch) {
    return `已完成第 ${batch[1]}/${batch[2]} 批评论分析，已分析 ${batch[3]}/${batch[4]} 条选中评论（采集总数 ${batch[5]} 条）。`;
  }
  if (event.event_type === "task.planning") return "执行服务已经领取任务，正在准备分析步骤。";
  if (event.event_type === "task.running") return "市场分析已经开始，页面会持续更新进度。";
  if (event.event_type === "task.completed") return "全部分析步骤已经完成，可以查看市场报告。";
  if (event.event_type === "task.degraded") return "分析已完成，部分数据受限，请结合报告中的限制说明阅读。";
  if (event.event_type === "task.failed") return "本次分析未能完成，请查看上方原因和处理建议。";
  if (event.event_type === "task.cancelled") return "任务已取消，已完成的执行记录仍然保留。";
  if (event.event_type === "task.cancel_requested") return "系统正在安全停止尚未完成的分析。";
  if (event.event_type === "node.started") return `正在${stepLabel(event.step)}。`;
  if (event.event_type === "node.completed") return `${stepLabel(event.step)}已经完成。`;
  if (event.event_type === "node.retrying") return "该步骤暂时未完成，系统正在自动重试。";
  if (event.event_type === "tool.started") return "正在读取或处理该步骤所需的数据。";
  if (event.event_type === "tool.completed") return "该步骤所需的数据已经处理完成。";
  if (event.event_type === "tool.failed") return "数据处理出现异常，系统已记录详细原因。";
  return "任务状态已更新。";
}

function time(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}
</script>

<template>
  <section class="progress-card" aria-labelledby="progress-title">
    <div class="progress-header">
      <div>
        <span class="eyebrow">任务 #{{ task.id.slice(0, 8) }}</span>
        <h2 id="progress-title">
          {{ statusCopy[task.status] }}<template v-if="degradedReason">（{{ degradedReason }}）</template>
        </h2>
        <p>当前阶段：{{ currentStage }}</p>
      </div>
      <div class="header-actions">
        <span v-if="streaming" class="live-indicator"><i></i>实时连接</span>
        <button
          v-if="canCancel"
          class="cancel-button"
          type="button"
          :disabled="cancelling"
          @click="emit('cancel')"
        >
          {{ cancelling ? "正在取消…" : "取消任务" }}
        </button>
      </div>
    </div>

    <div class="progress-track" aria-hidden="true"><span :style="{ width: `${progress}%` }"></span></div>
    <div class="progress-meta">
      <span>{{ progress }}%</span>
      <span>已完成 {{ completedSteps }} 个步骤<template v-if="task.retry_count"> · 自动重试 {{ task.retry_count }} 次</template></span>
    </div>

    <div v-if="task.error && taskError" class="task-error" role="alert">
      <span class="error-kicker">本次分析未完成</span>
      <strong>{{ taskError.title }}</strong>
      <dl>
        <div><dt>原因</dt><dd>{{ taskError.reason }}</dd></div>
        <div><dt>建议</dt><dd>{{ taskError.action }}</dd></div>
      </dl>
    </div>

    <div class="timeline-heading">
      <h3>执行动态</h3>
      <span>最新事件在前</span>
    </div>
    <div v-if="visibleEvents.length" class="timeline" aria-live="polite">
      <article v-for="event in visibleEvents" :key="event.event_id" class="event-row">
        <span class="event-dot" :class="eventTone(event)"></span>
        <div class="event-body">
          <div>
            <strong>{{ eventTitle(event) }}</strong>
            <time>{{ time(event.timestamp) }}</time>
          </div>
          <p>{{ eventDescription(event) }}</p>
          <span v-if="event.step" class="step-chip">{{ stepLabel(event.step) }}</span>
        </div>
      </article>
    </div>
    <div v-else class="empty-events">任务已经创建，等待第一条执行事件。</div>

    <details class="technical-details">
      <summary>查看技术详情</summary>
      <dl>
        <div><dt>任务 ID</dt><dd>{{ task.id }}</dd></div>
        <div><dt>Trace ID</dt><dd>{{ task.trace_id }}</dd></div>
        <div><dt>状态版本</dt><dd>{{ task.state_version }}</dd></div>
        <div><dt>重试次数</dt><dd>{{ task.retry_count }}</dd></div>
        <div v-if="task.error"><dt>错误码</dt><dd>{{ task.error.code }}</dd></div>
        <div v-if="task.error"><dt>原始错误</dt><dd>{{ task.error.message }}</dd></div>
        <div v-if="task.error?.step"><dt>停止节点</dt><dd>{{ task.error.step }}</dd></div>
      </dl>
      <pre v-if="errorDetails" class="error-details">{{ errorDetails }}</pre>
      <div v-if="visibleEvents.length" class="raw-events">
        <strong>最近原始事件</strong>
        <code v-for="event in visibleEvents" :key="`raw-${event.event_id}`">
          {{ time(event.timestamp) }} · {{ event.event_type }} · {{ event.step || "task" }} · {{ event.summary }}
        </code>
      </div>
    </details>
  </section>
</template>

<style scoped>
.progress-card {
  height: 100%;
  padding: clamp(1.25rem, 2.5vw, 2rem);
  color: #edf2ff;
  background: radial-gradient(circle at 90% 0, #344b76 0, transparent 32%), #151e31;
  border-radius: 18px;
  box-shadow: 0 18px 45px rgb(16 25 45 / 18%);
}
.progress-header,
.header-actions,
.progress-meta,
.timeline-heading,
.event-body > div { display: flex; align-items: center; justify-content: space-between; gap: 0.8rem; }
.progress-header { align-items: flex-start; }
.eyebrow { color: #9baacf; font-size: 0.7rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; }
h2 { margin: 0.35rem 0 0.2rem; color: #fff; font-size: 1.55rem; }
.progress-header p { margin: 0; color: #aebbd6; font-size: 0.82rem; }
.header-actions { flex-wrap: wrap; justify-content: flex-end; }
.live-indicator { display: flex; align-items: center; gap: 0.4rem; color: #c7d3eb; font-size: 0.72rem; }
.live-indicator i { width: 7px; height: 7px; background: #55d49a; border-radius: 50%; box-shadow: 0 0 0 4px rgb(85 212 154 / 15%); }
.cancel-button { padding: 0.45rem 0.7rem; color: #f4d8db; background: transparent; border: 1px solid #884c57; border-radius: 8px; font-size: 0.75rem; }
.cancel-button:disabled { opacity: 0.5; }
.progress-track { height: 6px; margin-top: 1.5rem; overflow: hidden; background: rgb(255 255 255 / 10%); border-radius: 999px; }
.progress-track span { display: block; height: 100%; background: linear-gradient(90deg, #6681ff, #51d6aa); border-radius: inherit; transition: width 0.35s ease; }
.progress-meta { margin-top: 0.45rem; color: #91a1c3; font-size: 0.68rem; }
.task-error { margin-top: 1rem; padding: 1rem; color: #ffe4e6; background: rgb(169 55 69 / 20%); border: 1px solid rgb(230 100 113 / 28%); border-radius: 10px; }
.error-kicker { color: #f2aab1; font-size: 0.62rem; font-weight: 800; letter-spacing: 0.08em; }
.task-error > strong { display: block; margin-top: 0.2rem; color: #fff; font-size: 0.95rem; }
.task-error dl { display: grid; gap: 0.55rem; margin: 0.75rem 0 0; }
.task-error dl div { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 0.5rem; }
.task-error dt { color: #f2aab1; font-size: 0.68rem; font-weight: 700; }
.task-error dd { margin: 0; color: #f5d9dc; font-size: 0.72rem; line-height: 1.5; }
.timeline-heading { margin: 1.6rem 0 0.8rem; }
.timeline-heading h3 { margin: 0; font-size: 0.95rem; }
.timeline-heading span { color: #91a1c3; font-size: 0.68rem; }
.timeline { max-height: 490px; padding-right: 0.3rem; overflow: auto; }
.event-row { position: relative; display: grid; grid-template-columns: 16px 1fr; gap: 0.65rem; padding: 0.55rem 0; }
.event-row:not(:last-child)::after { position: absolute; top: 1.3rem; bottom: -0.3rem; left: 5px; width: 1px; background: rgb(255 255 255 / 12%); content: ""; }
.event-dot { z-index: 1; width: 11px; height: 11px; margin-top: 0.27rem; background: #7890c8; border: 2px solid #151e31; border-radius: 50%; box-shadow: 0 0 0 2px #7890c8; }
.event-dot.success { background: #4bc38d; box-shadow: 0 0 0 2px #4bc38d; }
.event-dot.warning { background: #e0ae4f; box-shadow: 0 0 0 2px #e0ae4f; }
.event-dot.danger { background: #e66f7b; box-shadow: 0 0 0 2px #e66f7b; }
.event-body strong { color: #f3f6ff; font-size: 0.78rem; }
.event-body time { color: #7f90b2; font-size: 0.65rem; }
.event-body p { margin: 0.18rem 0; color: #aebbd6; font-size: 0.73rem; line-height: 1.45; }
.step-chip { display: inline-block; padding: 0.15rem 0.4rem; color: #9eb5f3; background: rgb(105 134 215 / 13%); border-radius: 5px; font-size: 0.64rem; }
.empty-events { padding: 2rem 0; color: #91a1c3; text-align: center; font-size: 0.78rem; }
.technical-details { margin-top: 1rem; padding-top: 0.8rem; color: #91a1c3; border-top: 1px solid rgb(255 255 255 / 10%); font-size: 0.68rem; }
.technical-details summary { width: fit-content; color: #aebbd6; cursor: pointer; font-weight: 700; }
.technical-details > dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.45rem 1rem; margin: 0.8rem 0 0; }
.technical-details > dl div { min-width: 0; }
.technical-details dt { color: #7182a4; }
.technical-details dd { margin: 0.12rem 0 0; overflow-wrap: anywhere; color: #b7c3dc; }
.error-details { margin: 0.8rem 0 0; padding: 0.55rem; overflow: auto; color: #9fb0d3; background: rgb(255 255 255 / 4%); border-radius: 5px; font-size: 0.58rem; white-space: pre-wrap; }
.raw-events { display: grid; gap: 0.35rem; margin-top: 0.9rem; }
.raw-events > strong { color: #aebbd6; }
.raw-events code { padding: 0.4rem; overflow-wrap: anywhere; color: #8fa2ca; background: rgb(255 255 255 / 4%); border-radius: 5px; font-size: 0.58rem; white-space: normal; }
@media (max-width: 575px) {
  .progress-header { flex-direction: column; }
  .header-actions { width: 100%; justify-content: space-between; }
  .technical-details > dl { grid-template-columns: 1fr; }
}
</style>
