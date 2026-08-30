<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import { hasPermission } from "../../../auth/session";
import {
  getMarketMetricBatch,
  listMarketMetricBatches,
  MarketIntelligenceApiError,
  uploadMarketMetrics,
} from "../api/marketIntelligence";
import type {
  MarketMetricBatch,
  MarketMetricBatchCreate,
  MarketMetricBatchDetail,
  MarketMetricBatchStatus,
  MarketMetricObservation,
  MarketMetricSourceType,
  MarketMetricUploadResult,
} from "../types/marketIntelligence";

const emit = defineEmits<{ back: [] }>();

const pageSize = 20;
const batches = ref<MarketMetricBatch[]>([]);
const total = ref(0);
const offset = ref(0);
const statusFilter = ref<"" | MarketMetricBatchStatus>("");
const listLoading = ref(false);
const listError = ref("");
const uploading = ref(false);
const uploadError = ref("");
const uploadResult = ref<MarketMetricUploadResult | null>(null);
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const dragging = ref(false);
const detail = ref<MarketMetricBatchDetail | null>(null);
const detailLoading = ref(false);
const detailError = ref("");
const canUpload = computed(() => hasPermission("market_metric:write"));

function localDate(date: Date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

const now = new Date();
const start = new Date(now.getFullYear(), 0, 1);
const form = reactive({
  platform: "amazon",
  market: "US",
  category: "",
  keyword: "",
  period_start: localDate(start),
  period_end: localDate(now),
  source_name: "",
  source_type: "manual_import" as MarketMetricSourceType,
  source_description: "",
  source_timestamp: localDate(now),
  methodology: "按上传文件中的指标值与统计周期汇总，系统按统一公式计算衍生指标。",
  license_or_authorization: "",
  data_version: `v${now.toISOString().slice(0, 10).replaceAll("-", "")}`,
});

const statusCopy: Record<MarketMetricBatchStatus, string> = {
  pending_review: "等待审核",
  approved: "审核通过",
  rejected: "审核驳回",
  disabled: "已停用",
};
const sourceCopy: Record<MarketMetricSourceType, string> = {
  official_api: "官方 API",
  official_report: "官方报告",
  licensed_provider: "授权数据服务商",
  authorized_export: "授权数据导出",
  manual_import: "人工整理导入",
};
const metricCopy: Record<string, string> = {
  market_size: "市场规模",
  gmv: "商品交易总额（GMV）",
  sales_volume: "销售量",
  order_count: "订单量",
  active_product_count: "活跃商品数",
  active_brand_count: "活跃品牌数",
  category_traffic: "类目流量",
  growth: "增长率",
  cagr: "复合年增长率",
  average_transaction_price: "平均成交价",
  gmv_market_share: "GMV 市场占比",
};
const reviewCopy: Record<string, string> = {
  CORE_MARKET_METRIC_MISSING: "缺少市场规模或 GMV 核心指标",
  DIRECT_METRIC_NOT_AVAILABLE: "存在不可用的原始指标",
  SOURCE_TIMESTAMP_IN_FUTURE: "数据来源时间晚于当前时间",
  SOURCE_PRECEDES_PERIOD_END: "数据来源时间早于统计周期结束时间",
  SOURCE_FILE_MISSING: "缺少可追溯的来源文件",
  REPORTED_GROWTH_CONFLICT: "上报增长数据与系统计算结果冲突",
  TIMESTAMP_TIMEZONE_MISMATCH: "时间字段的时区口径不一致",
};

const resultTone = computed(() => uploadResult.value?.status ?? "pending_review");
const rangeStart = computed(() => total.value ? offset.value + 1 : 0);
const rangeEnd = computed(() => Math.min(offset.value + pageSize, total.value));

function readableError(error: unknown, fallback: string) {
  if (error instanceof MarketIntelligenceApiError) {
    if (error.status === 403) return "当前账号没有宏观市场指标操作权限。";
    return error.message;
  }
  return error instanceof Error ? error.message : fallback;
}

async function loadBatches(reset = false) {
  if (reset) offset.value = 0;
  listLoading.value = true;
  listError.value = "";
  try {
    const response = await listMarketMetricBatches({
      status: statusFilter.value || undefined,
      limit: pageSize,
      offset: offset.value,
    });
    batches.value = response.items;
    total.value = response.total;
  } catch (error) {
    listError.value = readableError(error, "批次记录加载失败。");
  } finally {
    listLoading.value = false;
  }
}

function selectFile(file?: File) {
  uploadError.value = "";
  uploadResult.value = null;
  if (!file) return;
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!extension || !["csv", "json", "xlsx"].includes(extension)) {
    uploadError.value = "请选择 CSV、JSON 或 XLSX 文件。";
    return;
  }
  selectedFile.value = file;
}

function onFileChange(event: Event) {
  selectFile((event.target as HTMLInputElement).files?.[0]);
}

function onDrop(event: DragEvent) {
  dragging.value = false;
  selectFile(event.dataTransfer?.files[0]);
}

function removeFile() {
  selectedFile.value = null;
  if (fileInput.value) fileInput.value.value = "";
}

function toIsoDate(value: string, endOfDay = false) {
  const suffix = endOfDay ? "T23:59:59.999" : "T00:00:00.000";
  return new Date(`${value}${suffix}`).toISOString();
}

async function submitUpload() {
  uploadError.value = "";
  uploadResult.value = null;
  if (!selectedFile.value) {
    uploadError.value = "请先选择指标文件。";
    return;
  }
  if (new Date(form.period_end) < new Date(form.period_start)) {
    uploadError.value = "统计周期结束时间不能早于开始时间。";
    return;
  }
  const batch: MarketMetricBatchCreate = {
    platform: form.platform.trim(),
    market: form.market.trim().toUpperCase(),
    category: form.category.trim(),
    keyword: form.keyword.trim(),
    period_start: toIsoDate(form.period_start),
    period_end: toIsoDate(form.period_end, true),
    source_name: form.source_name.trim(),
    source_type: form.source_type,
    source_description: form.source_description.trim() || null,
    source_timestamp: toIsoDate(form.source_timestamp, true),
    methodology: form.methodology.trim(),
    license_or_authorization: form.license_or_authorization.trim(),
    data_version: form.data_version.trim(),
  };
  uploading.value = true;
  try {
    uploadResult.value = await uploadMarketMetrics(batch, selectedFile.value);
    removeFile();
    await loadBatches(true);
  } catch (error) {
    uploadError.value = readableError(error, "上传失败，请检查文件内容与来源信息。");
  } finally {
    uploading.value = false;
  }
}

async function openDetail(batchId: string) {
  detail.value = null;
  detailError.value = "";
  detailLoading.value = true;
  try {
    detail.value = await getMarketMetricBatch(batchId);
  } catch (error) {
    detailError.value = readableError(error, "批次详情加载失败。");
  } finally {
    detailLoading.value = false;
  }
}

function closeDetail() {
  detail.value = null;
  detailError.value = "";
  detailLoading.value = false;
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(value));
}

function formatDateTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" })
    .format(new Date(value));
}

function formatMetric(item: MarketMetricObservation) {
  if (item.value === null) return "暂无数据";
  const numeric = Number(item.value);
  const value = Number.isFinite(numeric)
    ? numeric.toLocaleString("zh-CN", { maximumFractionDigits: 4 })
    : String(item.value);
  return `${value}${item.unit ? ` ${item.unit}` : ""}`;
}

function metricName(code: string) {
  return metricCopy[code] ?? code.replaceAll("_", " ");
}

function reviewReason(code: string) {
  return reviewCopy[code] ?? code;
}

function previousPage() {
  offset.value = Math.max(0, offset.value - pageSize);
  void loadBatches();
}

function nextPage() {
  offset.value += pageSize;
  void loadBatches();
}

onMounted(() => void loadBatches());
</script>

<template>
  <main class="metric-shell">
    <header class="page-header">
      <div>
        <button type="button" class="back-link" @click="emit('back')">← 返回市场概览</button>
        <span>MACRO MARKET DATA</span>
        <h1>宏观市场指标管理</h1>
        <p>上传市场数据，审核通过后供市场情报 Agent 使用。</p>
      </div>
      <div class="header-note"><i></i><span>系统自动审核</span><small>上传后即时给出结果</small></div>
    </header>

    <section v-if="canUpload" class="upload-card">
      <div class="section-title">
        <div><b>01</b><div><h2>登记指标批次</h2><p>范围与来源信息会成为报告证据的一部分</p></div></div>
        <span>必填项已标注 *</span>
      </div>
      <form @submit.prevent="submitUpload">
        <div class="form-grid scope-grid">
          <label><span>分析平台 *</span><input v-model="form.platform" required placeholder="例如 amazon" /></label>
          <label><span>目标市场 *</span><input v-model="form.market" required maxlength="16" placeholder="例如 US" /></label>
          <label><span>业务类目 *</span><input v-model="form.category" required placeholder="例如 home_and_kitchen" /></label>
          <label><span>商品关键词 *</span><input v-model="form.keyword" required placeholder="例如 portable blender" /></label>
          <label><span>统计周期开始 *</span><input v-model="form.period_start" required type="date" /></label>
          <label><span>统计周期结束 *</span><input v-model="form.period_end" required type="date" /></label>
        </div>

        <div class="form-divider"><span>数据来源</span></div>
        <div class="form-grid source-grid">
          <label><span>来源名称 *</span><input v-model="form.source_name" required placeholder="报告、接口或数据商名称" /></label>
          <label><span>来源类型 *</span><select v-model="form.source_type"><option v-for="(label, value) in sourceCopy" :key="value" :value="value">{{ label }}</option></select></label>
          <label><span>数据发布日期 *</span><input v-model="form.source_timestamp" required type="date" /></label>
          <label><span>数据版本 *</span><input v-model="form.data_version" required placeholder="例如 2026-Q2" /></label>
          <label class="wide"><span>统计方法 *</span><textarea v-model="form.methodology" required rows="2" placeholder="简要说明统计口径、样本范围与计算方法"></textarea><small class="form-help">已提供通用口径，可根据实际数据来源修改。</small></label>
          <label class="wide"><span>授权或许可说明 *</span><textarea v-model="form.license_or_authorization" required rows="2" placeholder="说明数据使用授权、许可编号或内部审批依据"></textarea></label>
          <label class="wide"><span>来源补充说明</span><input v-model="form.source_description" placeholder="可选：报告页码、接口版本或其他追溯信息" /></label>
        </div>

        <div class="form-divider"><span>指标文件</span></div>
        <div
          class="drop-zone"
          :class="{ dragging, selected: selectedFile }"
          @dragenter.prevent="dragging = true"
          @dragover.prevent
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <input ref="fileInput" type="file" accept=".csv,.json,.xlsx" @change="onFileChange" />
          <template v-if="selectedFile">
            <div class="file-icon">✓</div>
            <div><strong>{{ selectedFile.name }}</strong><small>{{ (selectedFile.size / 1024).toFixed(1) }} KB · 等待上传</small></div>
            <button type="button" @click.stop="removeFile">移除</button>
          </template>
          <template v-else>
            <div class="file-icon">↑</div>
            <div><strong>拖入文件，或点击选择</strong><small>支持 CSV、JSON、XLSX 格式</small></div>
          </template>
        </div>
        <div class="file-guide">
          <div>
            <strong>文件中每一行代表一项市场指标，需要填写：</strong>
            <ul>
              <li><b>指标名称</b>：系统识别码，例如市场规模填写 <code>market_size</code>，GMV 填写 <code>gmv</code></li>
              <li><b>指标数值</b>：只填写数字，例如 <code>1200000</code></li>
              <li><b>计量单位</b>：金额填写 <code>USD</code>，销量填写 <code>units</code>，订单量填写 <code>orders</code></li>
            </ul>
          </div>
          <a href="/examples/market_metric_upload_example.csv" download>下载可用的 CSV 示例</a>
        </div>

        <div v-if="uploadError" class="notice error" role="alert">{{ uploadError }}</div>
        <div v-if="uploadResult" class="result-card" :class="resultTone">
          <div class="result-symbol">{{ uploadResult.status === 'approved' ? '✓' : '!' }}</div>
          <div>
            <span>系统审核结果</span>
            <strong>{{ statusCopy[uploadResult.status] }}</strong>
            <p>
              已读取 {{ uploadResult.direct_metric_count }} 项原始指标，生成
              {{ uploadResult.derived_metric_count }} 项系统计算指标。
            </p>
            <ul v-if="uploadResult.approval_codes.length">
              <li v-for="code in uploadResult.approval_codes" :key="code">{{ reviewReason(code) }}</li>
            </ul>
          </div>
          <button type="button" @click="openDetail(uploadResult.batch_id)">查看批次</button>
        </div>

        <div class="submit-row">
          <p>核心指标需包含“市场规模”或“GMV”，系统派生指标无需手工上传。</p>
          <button type="submit" :disabled="uploading">{{ uploading ? "正在上传并审核…" : "上传并自动审核" }}</button>
        </div>
      </form>
    </section>

    <section v-else class="permission-card">
      <div>只读</div><p>当前账号可以查看宏观指标批次。上传需要 <code>market_metric:write</code> 权限。</p>
    </section>

    <section class="batch-card">
      <div class="section-title list-title">
        <div><b>02</b><div><h2>指标批次</h2><p>仅审核通过的数据会进入 Agent 的宏观市场分析</p></div></div>
        <div class="list-actions">
          <select v-model="statusFilter" aria-label="按审核状态筛选" @change="loadBatches(true)">
            <option value="">全部状态</option>
            <option v-for="(label, value) in statusCopy" :key="value" :value="value">{{ label }}</option>
          </select>
          <button type="button" :disabled="listLoading" @click="loadBatches()">刷新</button>
        </div>
      </div>

      <div v-if="listError" class="notice error" role="alert">{{ listError }}</div>
      <div v-if="listLoading && !batches.length" class="empty-state">正在读取指标批次…</div>
      <div v-else-if="!batches.length" class="empty-state"><strong>暂无指标批次</strong><span>上传第一份市场宏观数据后，记录会显示在这里。</span></div>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>分析范围</th><th>统计周期</th><th>数据来源</th><th>审核状态</th><th>上传时间</th><th></th></tr></thead>
          <tbody>
            <tr v-for="batch in batches" :key="batch.id">
              <td><strong>{{ batch.keyword }}</strong><span>{{ batch.platform.toUpperCase() }} · {{ batch.market }} · {{ batch.category }}</span></td>
              <td>{{ formatDate(batch.period_start) }}<span>至 {{ formatDate(batch.period_end) }}</span></td>
              <td>{{ batch.source_name }}<span>{{ sourceCopy[batch.source_type] }} · {{ batch.data_version }}</span></td>
              <td><span class="status-pill" :class="batch.status"><i></i>{{ statusCopy[batch.status] }}</span><small v-if="batch.review_codes.length">{{ batch.review_codes.length }} 项原因</small></td>
              <td>{{ formatDateTime(batch.created_at) }}<span>由 {{ batch.uploaded_by }} 上传</span></td>
              <td><button type="button" class="detail-button" @click="openDetail(batch.id)">查看详情 →</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer v-if="total" class="pagination">
        <span>第 {{ rangeStart }}–{{ rangeEnd }} 条，共 {{ total }} 条</span>
        <div><button type="button" :disabled="offset === 0 || listLoading" @click="previousPage">上一页</button><button type="button" :disabled="rangeEnd >= total || listLoading" @click="nextPage">下一页</button></div>
      </footer>
    </section>

    <div v-if="detailLoading || detail || detailError" class="drawer-layer" @click.self="closeDetail">
      <aside class="detail-drawer" aria-label="指标批次详情">
        <header><div><span>BATCH DETAIL</span><h2>指标批次详情</h2></div><button type="button" aria-label="关闭" @click="closeDetail">×</button></header>
        <div v-if="detailLoading" class="drawer-state">正在加载完整指标…</div>
        <div v-else-if="detailError" class="drawer-state error">{{ detailError }}</div>
        <template v-else-if="detail">
          <div class="detail-summary">
            <div><span>审核状态</span><strong class="status-pill" :class="detail.batch.status"><i></i>{{ statusCopy[detail.batch.status] }}</strong></div>
            <div><span>分析范围</span><strong>{{ detail.batch.platform.toUpperCase() }} · {{ detail.batch.market }} · {{ detail.batch.keyword }}</strong></div>
            <div><span>数据来源</span><strong>{{ detail.batch.source_name }} / {{ detail.batch.data_version }}</strong></div>
            <div><span>统计周期</span><strong>{{ formatDate(detail.batch.period_start) }} — {{ formatDate(detail.batch.period_end) }}</strong></div>
          </div>
          <div v-if="detail.batch.review_codes.length" class="review-reasons"><span>审核未通过原因</span><ul><li v-for="code in detail.batch.review_codes" :key="code">{{ reviewReason(code) }}<small>{{ code }}</small></li></ul></div>
          <section class="metric-section"><div><h3>原始指标</h3><span>{{ detail.direct_observations.length }} 项</span></div><div class="metric-list"><article v-for="item in detail.direct_observations" :key="item.id"><div><span>{{ item.metric_code }}</span><strong>{{ metricName(item.metric_code) }}</strong></div><b>{{ formatMetric(item) }}</b><small>{{ item.methodology }}</small></article></div></section>
          <section class="metric-section"><div><h3>系统计算指标</h3><span>{{ detail.derived_observations.length }} 项</span></div><div v-if="detail.derived_observations.length" class="metric-list"><article v-for="item in detail.derived_observations" :key="item.id"><div><span>{{ item.formula_code || item.metric_code }}</span><strong>{{ metricName(item.metric_code) }}</strong></div><b>{{ formatMetric(item) }}</b><small>公式版本 {{ item.formula_version }} · {{ item.source_observation_ids.length }} 个来源指标</small></article></div><p v-else class="inline-empty">当前批次没有可计算的衍生指标。</p></section>
          <section class="provenance"><h3>来源与追溯</h3><dl><div><dt>来源类型</dt><dd>{{ sourceCopy[detail.batch.source_type] }}</dd></div><div><dt>数据发布时间</dt><dd>{{ formatDate(detail.batch.source_timestamp) }}</dd></div><div><dt>统计方法</dt><dd>{{ detail.batch.methodology }}</dd></div><div><dt>授权说明</dt><dd>{{ detail.batch.license_or_authorization }}</dd></div><div><dt>文件摘要 SHA-256</dt><dd class="hash">{{ detail.batch.original_file_sha256 || '—' }}</dd></div><div><dt>追踪编号</dt><dd class="hash">{{ detail.batch.trace_id }}</dd></div></dl></section>
        </template>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.metric-shell { --ink: #17233d; --muted: #6f7c92; max-width: 1320px; margin: 0 auto; padding-bottom: 2.5rem; color: var(--ink); }
.page-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 2rem; padding: .5rem 0 1.2rem; }
.back-link { display: block; margin: 0 0 .55rem; padding: 0; color: #526a9f; background: transparent; border: 0; font-size: .72rem; font-weight: 750; }
.page-header > div > span { color: #526a9f; font-size: .67rem; font-weight: 850; letter-spacing: .16em; }
.page-header h1 { margin: .28rem 0; font-size: clamp(1.75rem, 3vw, 2.45rem); letter-spacing: -.035em; }
.page-header p { max-width: 760px; margin: 0; color: var(--muted); line-height: 1.65; }
.header-note { display: grid; flex: 0 0 auto; grid-template-columns: auto auto; column-gap: .5rem; align-items: center; padding: .8rem 1rem; background: #edf7f2; border: 1px solid #cae6d7; border-radius: 12px; }
.header-note i { width: 8px; height: 8px; grid-row: 1 / 3; background: #36a371; border-radius: 50%; box-shadow: 0 0 0 5px rgb(54 163 113 / 12%); }
.header-note span { color: #235f45; font-size: .72rem; font-weight: 800; }.header-note small { color: #688578; font-size: .62rem; }
.upload-card,.batch-card,.permission-card { margin-top: 1rem; padding: 1.25rem; background: #fff; border: 1px solid #dfe5ed; border-radius: 15px; }
.section-title,.section-title > div { display: flex; align-items: center; justify-content: space-between; gap: .7rem; }.section-title { margin-bottom: 1.2rem; }.section-title b { color: #8a96a9; font-size: .68rem; }.section-title h2 { margin: 0; font-size: 1rem; }.section-title p { margin: .12rem 0 0; color: #8490a3; font-size: .66rem; }.section-title > span { color: #8a96a9; font-size: .62rem; }
.form-grid { display: grid; gap: .85rem; }.scope-grid { grid-template-columns: repeat(4,1fr); }.source-grid { grid-template-columns: repeat(4,1fr); }.form-grid label { display: flex; min-width: 0; flex-direction: column; gap: .36rem; }.form-grid label.wide { grid-column: span 2; }.form-grid label > span { color: #55637a; font-size: .65rem; font-weight: 750; }
input,select,textarea { width: 100%; padding: .64rem .72rem; color: #253149; background: #fbfcfe; border: 1px solid #d7deea; border-radius: 8px; outline: none; font: inherit; font-size: .72rem; } textarea { resize: vertical; line-height: 1.5; } input:focus,select:focus,textarea:focus { border-color: #5572c5; box-shadow: 0 0 0 3px rgb(70 100 188 / 10%); }
.form-divider { display: flex; align-items: center; gap: .75rem; margin: 1.25rem 0 .9rem; color: #718096; font-size: .63rem; font-weight: 800; text-transform: uppercase; }.form-divider::after { height: 1px; background: #e9edf3; content: ''; flex: 1; }
.drop-zone { position: relative; display: flex; min-height: 92px; align-items: center; gap: .8rem; padding: 1rem; background: #f8faff; border: 1px dashed #b9c5db; border-radius: 11px; transition: .16s ease; }.drop-zone.dragging { background: #edf2ff; border-color: #4664bc; }.drop-zone.selected { border-style: solid; }.drop-zone > input { position: absolute; inset: 0; z-index: 1; opacity: 0; cursor: pointer; }.drop-zone button { z-index: 2; margin-left: auto; color: #8a4650; background: transparent; border: 0; font-size: .66rem; font-weight: 750; }.file-icon { display: grid; width: 38px; height: 38px; flex: 0 0 auto; color: #3e5faf; background: #e7edff; border-radius: 10px; place-items: center; font-weight: 850; }.drop-zone strong,.drop-zone small { display: block; }.drop-zone strong { font-size: .75rem; }.drop-zone small { margin-top: .22rem; color: #7d899e; font-size: .63rem; }
.file-guide { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-top: .65rem; padding: .8rem .9rem; color: #647188; background: #f7f9fc; border: 1px solid #e5eaf1; border-radius: 9px; font-size: .75rem; line-height: 1.55; }.file-guide strong { color: #42506a; }.file-guide ul { display: flex; flex-wrap: wrap; gap: .15rem 1.1rem; margin: .3rem 0 0; padding: 0; list-style: none; }.file-guide li { position: relative; padding-left: .7rem; }.file-guide li::before { position: absolute; left: 0; color: #4d69b4; content: '•'; }.file-guide code { color: #405b9d; font-size: .72rem; }.file-guide a { flex: 0 0 auto; padding: .55rem .7rem; color: #3456a5; background: #fff; border: 1px solid #cbd5e6; border-radius: 7px; font-weight: 800; text-decoration: none; white-space: nowrap; }.file-guide a:hover { background: #edf2ff; border-color: #aebddd; }
.notice { margin-top: .8rem; padding: .75rem .85rem; border-radius: 8px; font-size: .7rem; }.notice.error,.drawer-state.error { color: #873e48; background: #fff3f4; border: 1px solid #efcdd1; }
.result-card { display: grid; grid-template-columns: auto minmax(0,1fr) auto; align-items: center; gap: .85rem; margin-top: .85rem; padding: .85rem; color: #285f47; background: #edf8f2; border: 1px solid #cbe8d8; border-radius: 10px; }.result-card.rejected { color: #843e48; background: #fff3f4; border-color: #efcdd1; }.result-card.pending_review { color: #765d23; background: #fff9e9; border-color: #eadcae; }.result-symbol { display: grid; width: 32px; height: 32px; background: currentColor; border-radius: 50%; color: #fff; place-items: center; font-weight: 850; }.result-card span,.result-card strong { display: block; }.result-card span { font-size: .58rem; opacity: .75; }.result-card strong { font-size: .86rem; }.result-card p { margin: .2rem 0 0; font-size: .67rem; }.result-card ul { margin: .35rem 0 0; padding-left: 1rem; font-size: .65rem; }.result-card button { color: inherit; background: transparent; border: 0; font-size: .65rem; font-weight: 800; }
.submit-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-top: 1rem; }.submit-row p { margin: 0; color: #7c899d; font-size: .65rem; }.submit-row button { padding: .7rem 1rem; color: #fff; background: #3456b2; border: 0; border-radius: 9px; font-size: .72rem; font-weight: 800; box-shadow: 0 7px 18px rgb(52 86 178 / 18%); }.submit-row button:disabled { cursor: wait; opacity: .65; }
.permission-card { display: flex; align-items: center; gap: .75rem; }.permission-card > div { padding: .28rem .5rem; color: #6f5b24; background: #fff2c8; border-radius: 5px; font-size: .62rem; font-weight: 800; }.permission-card p { margin: 0; color: #718096; font-size: .7rem; }.permission-card code { color: #42577f; }
.list-title { align-items: flex-end; }.list-actions { display: flex; gap: .5rem; }.list-actions select { width: auto; min-width: 118px; padding: .5rem .65rem; }.list-actions button,.pagination button { padding: .5rem .7rem; color: #425b96; background: #f3f6fb; border: 1px solid #d9e0eb; border-radius: 7px; font-size: .65rem; font-weight: 750; }
.table-wrap { overflow-x: auto; }.table-wrap table { width: 100%; border-collapse: collapse; }.table-wrap th { padding: .62rem .7rem; color: #7d899c; background: #f5f7fa; font-size: .61rem; text-align: left; white-space: nowrap; }.table-wrap td { padding: .8rem .7rem; border-bottom: 1px solid #e9edf2; font-size: .68rem; vertical-align: middle; }.table-wrap tr:last-child td { border-bottom: 0; }.table-wrap td > strong,.table-wrap td > span { display: block; }.table-wrap td > span { margin-top: .18rem; color: #8994a6; font-size: .61rem; white-space: nowrap; }.table-wrap td > small { display: block; margin-top: .2rem; color: #9a6670; font-size: .58rem; }
.status-pill { display: inline-flex!important; width: max-content; align-items: center; gap: .35rem; padding: .24rem .46rem; color: #5a677c!important; background: #edf0f4; border-radius: 5px; font-size: .61rem!important; font-weight: 750; }.status-pill i { width: 6px; height: 6px; background: currentColor; border-radius: 50%; }.status-pill.approved { color: #276548!important; background: #e6f5ed; }.status-pill.rejected { color: #8b424c!important; background: #fbeaec; }.status-pill.pending_review { color: #7d6225!important; background: #fff3ce; }.detail-button { color: #3e5ca8; background: transparent; border: 0; font-size: .63rem; font-weight: 800; white-space: nowrap; }.empty-state { display: flex; min-height: 150px; align-items: center; justify-content: center; color: #8490a4; background: #f8f9fb; border-radius: 9px; flex-direction: column; font-size: .72rem; }.empty-state span { margin-top: .25rem; font-size: .65rem; }.pagination { display: flex; align-items: center; justify-content: space-between; margin-top: .8rem; color: #7e8a9d; font-size: .63rem; }.pagination div { display: flex; gap: .4rem; }.pagination button:disabled { opacity: .45; }
.drawer-layer { position: fixed; z-index: 1100; inset: 0; display: flex; justify-content: flex-end; background: rgb(19 28 47 / 42%); backdrop-filter: blur(2px); }.detail-drawer { width: min(620px,100%); height: 100%; overflow-y: auto; padding: 1.25rem; background: #fff; box-shadow: -18px 0 45px rgb(17 28 50 / 16%); }.detail-drawer > header { display: flex; align-items: center; justify-content: space-between; padding-bottom: .9rem; border-bottom: 1px solid #e7ebf1; }.detail-drawer header span { color: #6478a5; font-size: .61rem; font-weight: 850; letter-spacing: .14em; }.detail-drawer h2 { margin: .15rem 0 0; font-size: 1.2rem; }.detail-drawer header button { width: 34px; height: 34px; color: #69758a; background: #f1f3f7; border: 0; border-radius: 50%; font-size: 1.25rem; }.drawer-state { margin-top: 1rem; padding: 2rem; color: #7c889b; background: #f7f8fa; border-radius: 9px; text-align: center; }
.detail-summary { display: grid; grid-template-columns: 1fr 1fr; gap: .65rem; margin-top: 1rem; }.detail-summary > div { min-width: 0; padding: .75rem; background: #f7f9fc; border-radius: 8px; }.detail-summary span,.detail-summary strong { display: block; }.detail-summary span { color: #8591a4; font-size: .59rem; }.detail-summary strong { overflow-wrap: anywhere; margin-top: .22rem; font-size: .68rem; }
.review-reasons { margin-top: .85rem; padding: .8rem; color: #823f49; background: #fff4f5; border: 1px solid #efd1d5; border-radius: 9px; }.review-reasons > span { font-size: .63rem; font-weight: 800; }.review-reasons ul { margin: .45rem 0 0; padding: 0; list-style: none; }.review-reasons li { display: flex; justify-content: space-between; gap: .6rem; padding: .25rem 0; font-size: .66rem; }.review-reasons small { opacity: .65; font-family: monospace; }
.metric-section,.provenance { margin-top: 1rem; }.metric-section > div:first-child { display: flex; align-items: center; justify-content: space-between; margin-bottom: .55rem; }.metric-section h3,.provenance h3 { margin: 0; font-size: .78rem; }.metric-section > div:first-child span { color: #8490a3; font-size: .61rem; }.metric-list { display: grid; gap: .5rem; }.metric-list article { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: .4rem .8rem; padding: .72rem; background: #f7f9fc; border: 1px solid #e8ecf2; border-radius: 8px; }.metric-list article span,.metric-list article strong { display: block; }.metric-list article span { color: #7586aa; font: .56rem monospace; text-transform: uppercase; }.metric-list article strong { margin-top: .1rem; font-size: .7rem; }.metric-list article b { font-size: .73rem; }.metric-list article small { grid-column: 1 / 3; overflow-wrap: anywhere; color: #8692a5; font-size: .59rem; }.inline-empty { padding: 1rem; color: #8591a4; background: #f7f8fa; border-radius: 8px; font-size: .67rem; text-align: center; }
.provenance dl { margin: .55rem 0 0; padding: .2rem .75rem; background: #f7f9fc; border-radius: 8px; }.provenance dl > div { display: grid; grid-template-columns: 110px minmax(0,1fr); gap: .75rem; padding: .55rem 0; border-bottom: 1px solid #e7ebf0; }.provenance dl > div:last-child { border-bottom: 0; }.provenance dt { color: #7f8b9e; font-size: .61rem; }.provenance dd { margin: 0; overflow-wrap: anywhere; font-size: .65rem; }.provenance dd.hash { font-family: monospace; font-size: .58rem; }
/* 运营页面保持紧凑布局，同时保证正文和辅助信息清晰可读。 */
.back-link { font-size: .82rem; }
.page-header > div > span { font-size: .76rem; }
.header-note span { font-size: .82rem; }
.header-note small { font-size: .72rem; }
.section-title b { font-size: .77rem; }
.section-title h2 { font-size: 1.08rem; }
.section-title p { font-size: .76rem; }
.section-title > span { font-size: .72rem; }
.form-grid label > span { font-size: .78rem; }
.form-help { color: #8290a5; font-size: .7rem; line-height: 1.45; }
input,select,textarea { padding: .68rem .76rem; font-size: .82rem; }
.form-divider { font-size: .73rem; }
.drop-zone button { font-size: .76rem; }
.drop-zone strong { font-size: .85rem; }
.drop-zone small { font-size: .74rem; }
.notice { font-size: .8rem; }
.result-card span { font-size: .68rem; }
.result-card strong { font-size: .96rem; }
.result-card p { font-size: .78rem; }
.result-card ul,.result-card button { font-size: .76rem; }
.submit-row p { font-size: .76rem; }
.submit-row button { font-size: .82rem; }
.permission-card > div { font-size: .72rem; }
.permission-card p { font-size: .8rem; }
.list-actions select { min-width: 128px; }
.list-actions button,.pagination button { font-size: .76rem; }
.table-wrap th { font-size: .72rem; }
.table-wrap td { font-size: .79rem; }
.table-wrap td > span { font-size: .7rem; }
.table-wrap td > small { font-size: .68rem; }
.status-pill { font-size: .71rem!important; }
.detail-button { font-size: .73rem; }
.empty-state { font-size: .82rem; }
.empty-state span { font-size: .75rem; }
.pagination { font-size: .73rem; }
.detail-drawer header span { font-size: .71rem; }
.detail-summary span { font-size: .69rem; }
.detail-summary strong { font-size: .78rem; }
.review-reasons > span { font-size: .73rem; }
.review-reasons li { font-size: .76rem; }
.metric-section h3,.provenance h3 { font-size: .88rem; }
.metric-section > div:first-child span { font-size: .71rem; }
.metric-list article span { font-size: .66rem; }
.metric-list article strong { font-size: .8rem; }
.metric-list article b { font-size: .83rem; }
.metric-list article small { font-size: .69rem; }
.inline-empty { font-size: .77rem; }
.provenance dt { font-size: .71rem; }
.provenance dd { font-size: .75rem; }
.provenance dd.hash { font-size: .68rem; }
button { cursor: pointer; } button:focus-visible { outline: 2px solid #4664bc; outline-offset: 2px; }
@media (max-width: 991px) { .scope-grid,.source-grid { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 767px) { .page-header { align-items: stretch; flex-direction: column; }.header-note { align-self: flex-start; }.list-title,.submit-row { align-items: stretch; flex-direction: column; }.list-actions { width: 100%; }.list-actions select { flex: 1; }.result-card { grid-template-columns: auto 1fr; }.result-card button { grid-column: 2; justify-self: start; padding: 0; }.detail-summary { grid-template-columns: 1fr; } }
@media (max-width: 575px) { .scope-grid,.source-grid { grid-template-columns: 1fr; }.form-grid label.wide { grid-column: span 1; }.upload-card,.batch-card { padding: 1rem; }.section-title > span { display: none; }.submit-row button { width: 100%; }.file-guide { align-items: stretch; flex-direction: column; }.file-guide ul { flex-direction: column; }.file-guide a { text-align: center; }.provenance dl > div { grid-template-columns: 1fr; gap: .18rem; } }
</style>
