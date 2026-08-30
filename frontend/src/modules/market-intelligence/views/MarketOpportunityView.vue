<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { storeToRefs } from "pinia";

import { getMarketOverview } from "../api/marketIntelligence";
import EvidenceDrawer from "../components/EvidenceDrawer.vue";
import MarketIntelligenceForm from "../components/MarketIntelligenceForm.vue";
import MarketIntelligenceReport from "../components/MarketIntelligenceReport.vue";
import TaskProgress from "../components/TaskProgress.vue";
import { useMarketIntelligenceStore } from "../store/marketIntelligence";
import type { MarketOverview } from "../types/marketIntelligence";

const emit = defineEmits<{ metrics: [] }>();
const store = useMarketIntelligenceStore();
const coverage = ref<MarketOverview | null>(null);
const coverageLoading = ref(true);
const coverageError = ref(false);
const {
  userQuery,
  preview,
  draft,
  task,
  events,
  previewing,
  submitting,
  restoring,
  cancelling,
  streaming,
  error,
  fieldError,
  isTerminal,
  report,
  selectedEvidence,
  selectedEvidenceProduct,
} = storeToRefs(store);

async function loadCoverage() {
  coverageLoading.value = true;
  coverageError.value = false;
  try {
    coverage.value = await getMarketOverview();
  } catch {
    coverageError.value = true;
  } finally {
    coverageLoading.value = false;
  }
}

onMounted(() => {
  void store.restoreTask();
  void loadCoverage();
});
onBeforeUnmount(() => store.stopFollowing());
</script>

<template>
  <main class="market-opportunity">
    <header class="page-header">
      <div>
        <div class="page-kicker"><span></span> MARKET INTELLIGENCE AGENT</div>
        <h1>从商品想法，到有证据的市场判断</h1>
        <p>描述你想分析的商品，Agent 会核对可用数据、执行市场研究，并给出可追溯的进入建议。</p>
      </div>
      <button v-if="task && isTerminal" class="new-analysis" type="button" @click="store.startNewAnalysis">
        ＋ 新建分析
      </button>
    </header>

    <div v-if="error" class="global-error" role="alert">
      <div><strong>请求未完成</strong><span>{{ error }}</span></div>
      <button type="button" aria-label="关闭错误提示" @click="error = ''">×</button>
    </div>

    <div v-if="restoring" class="restore-card" aria-live="polite">
      <span class="spinner"></span>
      <div><strong>正在恢复上次分析</strong><p>读取任务状态、执行事件和已生成报告…</p></div>
    </div>

    <template v-else-if="!task">
      <div class="creation-layout">
        <MarketIntelligenceForm
          :query="userQuery"
          :preview="preview"
          :draft="draft"
          :previewing="previewing"
          :submitting="submitting"
          :field-error="fieldError"
          @update:query="store.updateQuery"
          @preview="store.runPreview"
          @submit="store.submitTask"
        />

        <aside class="method-card">
          <span class="method-index">HOW IT WORKS</span>
          <h2>先确认数据，再形成判断</h2>
          <ol>
            <li><i>1</i><div><strong>理解商品</strong><span>从自然语言提取市场、平台、类目和成本要求。</span></div></li>
            <li><i>2</i><div><strong>匹配数据</strong><span>核对固定数据集覆盖范围，提交前暴露缺失与歧义。</span></div></li>
            <li><i>3</i><div><strong>执行研究</strong><span>依次分析市场、竞品、评论与利润，并持续汇报进度。</span></div></li>
            <li><i>4</i><div><strong>追溯证据</strong><span>每个关键数字和结论都能回看样本与来源。</span></div></li>
          </ol>
          <div class="coverage-note">
            <span>当前数据覆盖</span>
            <small v-if="coverageLoading">正在读取有效数据集…</small>
            <small v-else-if="coverageError">覆盖信息暂时无法读取，不影响提交前的数据匹配检查。</small>
            <template v-else-if="coverage?.datasets.length">
              <div class="coverage-datasets">
                <strong v-for="dataset in coverage.datasets" :key="dataset.dataset_id">
                  {{ dataset.platform === "amazon" ? "Amazon" : dataset.platform }}
                  {{ dataset.market }} · {{ dataset.display_name }}
                </strong>
              </div>
            </template>
            <small v-else>当前没有通过校验的可用数据集。</small>
          </div>
        </aside>
      </div>
    </template>

    <template v-else>
      <div class="task-context">
        <div>
          <span>当前分析</span>
          <strong>{{ task.request.user_query }}</strong>
        </div>
        <div>
          <span>Trace ID</span>
          <code>{{ task.trace_id }}</code>
        </div>
      </div>

      <TaskProgress
        :task="task"
        :report="report"
        :events="events"
        :streaming="streaming"
        :cancelling="cancelling"
        @cancel="store.cancelCurrentTask"
      />

      <MarketIntelligenceReport
        v-if="report"
        :report="report"
        @evidence="store.showEvidence"
        @metrics="emit('metrics')"
      />

      <section v-else-if="task.status === 'FAILED'" class="terminal-message failed">
        <span>分析停止</span>
        <h2>任务未能生成有效报告</h2>
        <p>请查看上方的失败原因和处理建议；技术信息可以在“查看技术详情”中展开。</p>
      </section>
      <section v-else-if="task.status === 'CANCELLED'" class="terminal-message">
        <span>任务已结束</span>
        <h2>本次分析已经取消</h2>
        <p>已完成的执行事件仍保留在上方，可以新建分析重新开始。</p>
      </section>
    </template>

    <EvidenceDrawer
      v-if="selectedEvidence.length"
      :evidence="selectedEvidence"
      :product="selectedEvidenceProduct"
      @close="store.closeEvidence"
    />
  </main>
</template>

<style scoped>
.market-opportunity { --ink: #18233c; --muted: #6f7c92; max-width: 1320px; margin: 0 auto; padding-bottom: 2rem; }
.page-header { position: relative; display: flex; align-items: flex-end; justify-content: space-between; gap: 2rem; margin-bottom: 1.4rem; padding: 0.8rem 0 0.2rem; }
.page-header::after { position: absolute; right: 0; bottom: -0.7rem; width: 160px; height: 1px; background: linear-gradient(90deg, transparent, #8296c5); content: ""; }
.page-kicker { display: flex; align-items: center; gap: 0.55rem; color: #526a9f; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.15em; }
.page-kicker span { width: 24px; height: 2px; background: #526a9f; }
h1 { max-width: 760px; margin: 0.45rem 0; color: var(--ink); font-size: clamp(1.75rem, 3.2vw, 2.65rem); font-weight: 780; letter-spacing: -0.035em; }
.page-header p { max-width: 760px; margin: 0; color: var(--muted); font-size: 0.92rem; line-height: 1.65; }
.new-analysis { flex: 0 0 auto; padding: 0.7rem 1rem; color: #263b72; background: white; border: 1px solid #cad3e2; border-radius: 10px; font-weight: 750; }
.global-error { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; padding: 0.85rem 1rem; color: #74323a; background: #fcebec; border: 1px solid #efc7cb; border-radius: 11px; }
.global-error div { display: flex; gap: 0.25rem; flex-direction: column; font-size: 0.78rem; }
.global-error button { color: #74323a; background: transparent; border: 0; font-size: 1.25rem; }
.restore-card { display: flex; align-items: center; gap: 1rem; padding: 2rem; background: white; border: 1px solid var(--cui-border-color); border-radius: 16px; }
.restore-card p { margin: 0.2rem 0 0; color: var(--muted); font-size: 0.8rem; }
.spinner { width: 28px; height: 28px; border: 3px solid #dbe1ec; border-top-color: #4059ba; border-radius: 50%; animation: spin 0.8s linear infinite; }
.creation-layout { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(300px, 0.75fr); gap: 1rem; align-items: start; }
.method-card { position: sticky; top: 5.2rem; padding: 1.6rem; color: #eaf0ff; background: #18233d; border-radius: 18px; box-shadow: 0 18px 45px rgb(16 25 45 / 16%); }
.method-index { color: #8fa4d0; font-size: 0.66rem; font-weight: 800; letter-spacing: 0.13em; }
.method-card h2 { margin: 0.45rem 0 1.3rem; color: white; font-size: 1.3rem; }
.method-card ol { margin: 0; padding: 0; list-style: none; }
.method-card li { display: grid; grid-template-columns: 30px 1fr; gap: 0.7rem; padding: 0.7rem 0; border-bottom: 1px solid rgb(255 255 255 / 8%); }
.method-card li i { display: grid; width: 26px; height: 26px; color: #a9bae0; background: rgb(255 255 255 / 7%); border-radius: 7px; place-items: center; font-size: 0.66rem; font-style: normal; }
.method-card li div { display: flex; flex-direction: column; }
.method-card li strong { font-size: 0.78rem; }
.method-card li span { margin-top: 0.2rem; color: #9eacc9; font-size: 0.68rem; line-height: 1.45; }
.coverage-note { display: flex; margin-top: 1.2rem; padding: 0.9rem; color: #264d3d; background: #dff4e9; border-radius: 10px; flex-direction: column; }
.coverage-note span { font-size: 0.62rem; font-weight: 800; text-transform: uppercase; }
.coverage-datasets { display: grid; gap: 0.35rem; margin-top: 0.45rem; }
.coverage-datasets strong { display: block; padding: 0.32rem 0.45rem; overflow: hidden; color: #264d3d; background: rgb(255 255 255 / 65%); border: 1px solid #b9ddca; border-radius: 6px; font-size: 0.68rem; text-overflow: ellipsis; white-space: nowrap; }
.coverage-note small { margin-top: 0.25rem; color: #527565; font-size: 0.65rem; }
.task-context { display: grid; grid-template-columns: 1.4fr 0.8fr; gap: 1px; margin-bottom: 1rem; overflow: hidden; background: var(--cui-border-color); border: 1px solid var(--cui-border-color); border-radius: 12px; }
.task-context div { display: flex; min-width: 0; padding: 0.8rem 1rem; background: white; flex-direction: column; }
.task-context span { color: var(--muted); font-size: 0.65rem; }
.task-context strong,
.task-context code { margin-top: 0.2rem; overflow: hidden; color: var(--ink); font-size: 0.78rem; text-overflow: ellipsis; white-space: nowrap; }
.terminal-message { margin-top: 1rem; padding: 2rem; color: #536077; background: white; border: 1px solid #dfe5ed; border-radius: 15px; text-align: center; }
.terminal-message.failed { color: #793943; background: #fff8f8; border-color: #ebc9cd; }
.terminal-message span { font-size: 0.68rem; font-weight: 800; text-transform: uppercase; }
.terminal-message h2 { margin: 0.4rem 0; font-size: 1.2rem; }
.terminal-message p { margin: 0; font-size: 0.8rem; }
.terminal-message code { display: inline-block; margin-top: 0.7rem; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 2s; } }
@media (max-width: 991px) { .creation-layout { grid-template-columns: 1fr; } .method-card { position: static; } }
@media (max-width: 575px) { .page-header { align-items: stretch; flex-direction: column; } .new-analysis { width: 100%; } .task-context { grid-template-columns: 1fr; } }
</style>
