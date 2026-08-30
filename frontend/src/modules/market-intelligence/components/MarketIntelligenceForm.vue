<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { listMarketMetricCandidates } from "../api/marketIntelligence";
import type {
  DataSourceOption,
  MarketIntelligenceRequest,
  MarketMetricBatchCandidate,
  MarketMetricSourceType,
  ProfitCalculatorParameters,
  TaskPreviewResponse,
} from "../types/marketIntelligence";

const props = defineProps<{
  query: string;
  preview: TaskPreviewResponse | null;
  draft: MarketIntelligenceRequest | null;
  previewing: boolean;
  submitting: boolean;
  fieldError: string;
}>();
const emit = defineEmits<{
  "update:query": [value: string];
  preview: [];
  submit: [value: MarketIntelligenceRequest];
}>();

const editable = ref<MarketIntelligenceRequest | null>(null);
const marketInput = ref("");
const minimumMarginInput = ref("");
const marginError = ref("");
const marginNotice = ref("");
const profitEnabled = ref(false);
const metricCandidates = ref<MarketMetricBatchCandidate[]>([]);
const metricBatchesLoading = ref(false);
const metricBatchesError = ref("");
let metricBatchRequestVersion = 0;

const metricSourceCopy: Record<MarketMetricSourceType, string> = {
  official_api: "官方 API",
  official_report: "官方报告",
  licensed_provider: "授权数据服务商",
  authorized_export: "授权数据导出",
  manual_import: "人工整理导入",
};
const currencyOptions = [
  { code: "USD", name: "美元" },
  { code: "EUR", name: "欧元" },
  { code: "GBP", name: "英镑" },
  { code: "CNY", name: "人民币" },
  { code: "SEK", name: "瑞典克朗" },
  { code: "JPY", name: "日元" },
  { code: "CAD", name: "加元" },
  { code: "AUD", name: "澳元" },
] as const;

function cloneRequest(value: MarketIntelligenceRequest): MarketIntelligenceRequest {
  return JSON.parse(JSON.stringify(value)) as MarketIntelligenceRequest;
}

watch(
  () => props.draft,
  (value) => {
    editable.value = value ? cloneRequest(value) : null;
    marketInput.value = formatMarket(value?.market ?? "");
    minimumMarginInput.value = formatMinimumMargin(
      value?.profit_constraints?.minimum_margin ?? "",
    );
    marginError.value = "";
    marginNotice.value = "";
    profitEnabled.value = Boolean(value?.profit_constraints);
  },
  { immediate: true },
);

const sourceOptions = computed(() => props.preview?.data_source_options ?? []);
const marketChoices = computed(() => {
  const choices = new Map<string, { code: string; name: string; label: string }>();
  sourceOptions.value.forEach((option) => {
    const code = option.market.trim().toUpperCase();
    if (!code || choices.has(code)) return;
    const name = marketName(code);
    choices.set(code, { code, name, label: `${name}（${code}）` });
  });
  return [...choices.values()];
});
const visibleWarnings = computed(() =>
  (props.preview?.warnings ?? []).filter((warning) => {
    if (warning.code === "PROFIT_INPUT_MISSING") return false;
    if (
      warning.code === "PROFIT_INPUT_INCOMPLETE"
      && editable.value?.profit_constraints
    ) return false;
    return true;
  }),
);
const selectedSource = computed(() => {
  if (!editable.value) return null;
  return sourceOptions.value.find(
    (item) =>
      item.platform.toLowerCase() === editable.value?.platforms[0]?.toLowerCase() &&
      item.market.toLowerCase() === editable.value?.market.toLowerCase() &&
      item.data_source_mode === editable.value?.data_source_mode,
  ) ?? null;
});
const selectedSourceKey = computed({
  get: () => selectedSource.value ? sourceKey(selectedSource.value) : "",
  set: (value: string) => {
    if (!editable.value) return;
    const option = sourceOptions.value.find((item) => sourceKey(item) === value);
    if (!option || !option.available) return;
    editable.value.platforms = [option.platform];
    editable.value.market = option.market;
    marketInput.value = formatMarket(option.market);
    editable.value.data_source_mode = option.data_source_mode;
  },
});
const selectedMetricBatch = computed(() =>
  metricCandidates.value.find(
    (item) => item.batch.id === editable.value?.market_metric_batch_id,
  )?.batch ?? null,
);
const selectedProductMatch = computed(() =>
  metricCandidates.value.find(
    (item) => item.batch.id === editable.value?.market_metric_batch_id,
  )?.product_match ?? null,
);

async function loadMetricCandidates() {
  const requestVersion = ++metricBatchRequestVersion;
  const request = editable.value;
  const sourceAvailable = selectedSource.value?.available ?? false;
  const previousBatchId = request?.market_metric_batch_id ?? null;
  metricCandidates.value = [];
  metricBatchesError.value = "";
  if (request) {
    request.market_metric_batch_id = null;
    request.market_metric_product_match = null;
  }
  if (!request || !request.platforms[0] || !request.market || !request.category || !request.keyword || !sourceAvailable) {
    metricBatchesLoading.value = false;
    return;
  }
  metricBatchesLoading.value = true;
  try {
    const result = await listMarketMetricCandidates({
      platform: request.platforms[0],
      market: request.market,
      category: request.category,
      keyword: request.keyword,
      limit: 50,
    });
    if (requestVersion !== metricBatchRequestVersion) return;
    const candidates = [...result.items].sort((left, right) =>
      right.batch.period_end.localeCompare(left.batch.period_end)
      || right.batch.created_at.localeCompare(left.batch.created_at),
    );
    metricCandidates.value = candidates;
    if (!editable.value) return;
    const accepted = candidates.filter(candidateAccepted);
    editable.value.market_metric_batch_id = accepted.some(
      (item) => item.batch.id === previousBatchId,
    )
      ? previousBatchId
      : accepted[0]?.batch.id ?? null;
  } catch (caught) {
    if (requestVersion !== metricBatchRequestVersion) return;
    metricBatchesError.value = caught instanceof Error
      ? caught.message
      : "读取已审核宏观市场数据失败";
    if (editable.value) editable.value.market_metric_batch_id = null;
  } finally {
    if (requestVersion === metricBatchRequestVersion) metricBatchesLoading.value = false;
  }
}

watch(
  () => [
    editable.value?.platforms[0] ?? "",
    editable.value?.market ?? "",
    selectedSource.value?.available ?? false,
  ] as const,
  () => void loadMetricCandidates(),
  { immediate: true },
);
const canSubmit = computed(
  () =>
    Boolean(editable.value && selectedSource.value?.available) &&
    !props.preview?.missing_fields.length &&
    !metricBatchesLoading.value &&
    (!profitEnabled.value || parseMinimumMargin(minimumMarginInput.value).valid) &&
    !props.submitting,
);

function sourceKey(option: DataSourceOption) {
  return `${option.platform}|${option.market}|${option.data_source_mode}`;
}

function marketName(value: string) {
  const code = value.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return value.trim();
  try {
    return new Intl.DisplayNames(["zh-CN"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

function formatMarket(value: string) {
  const code = value.trim().toUpperCase();
  return /^[A-Z]{2}$/.test(code) ? `${marketName(code)}（${code}）` : value.trim();
}

function resolveMarket(value: string) {
  const raw = value.trim();
  const codeInLabel = raw.match(/[（(]\s*([a-z]{2})\s*[）)]$/i)?.[1];
  if (codeInLabel) return codeInLabel.toUpperCase();
  const choice = marketChoices.value.find((item) =>
    item.label.toLocaleLowerCase("zh-CN") === raw.toLocaleLowerCase("zh-CN")
    || item.name.toLocaleLowerCase("zh-CN") === raw.toLocaleLowerCase("zh-CN")
    || item.code.toLowerCase() === raw.toLowerCase(),
  );
  if (choice) return choice.code;
  return /^[a-z]{2}$/i.test(raw) ? raw.toUpperCase() : raw;
}

function commitMarket() {
  if (!editable.value) return;
  const market = resolveMarket(marketInput.value);
  editable.value.market = market;
  marketInput.value = formatMarket(market);
}

function sourceCapabilities(option: DataSourceOption) {
  const capabilities = [
    option.supports_products && "商品",
    option.supports_reviews && "评论",
    option.supports_market_metrics && "市场指标",
  ].filter(Boolean);
  return capabilities.length ? `支持：${capabilities.join("、")}` : option.unavailable_reason;
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN").format(new Date(value));
}

function candidateAccepted(candidate: MarketMetricBatchCandidate) {
  return candidate.product_match.decision === "same_product"
    && candidate.product_match.confidence >= 0.85;
}

function metricBatchLabel(candidate: MarketMetricBatchCandidate) {
  const batch = candidate.batch;
  const result = candidateAccepted(candidate) ? "商品一致" : "商品不一致或无法确认";
  return `${result} · ${batch.source_name} · ${shortDate(batch.period_start)}—${shortDate(batch.period_end)} · ${batch.keyword}`;
}

function productMatchLabel(decision: MarketMetricBatchCandidate["product_match"]["decision"]) {
  return {
    same_product: "商品一致",
    different_product: "商品不一致",
    uncertain: "无法确认商品一致性",
  }[decision];
}

function defaultProfit(): ProfitCalculatorParameters {
  return {
    schema_version: "1.0",
    price: "49.99",
    product_cost: "18",
    platform_fee: "7.5",
    logistics_cost: "6",
    advertising_cost: "5",
    minimum_margin: "0.30",
    currency: defaultCurrency(editable.value?.market ?? ""),
  };
}

function defaultCurrency(market: string) {
  const marketCurrency: Record<string, string> = {
    US: "USD",
    SE: "SEK",
    GB: "GBP",
    CN: "CNY",
    JP: "JPY",
    CA: "CAD",
    AU: "AUD",
    DE: "EUR",
    FR: "EUR",
    IT: "EUR",
    ES: "EUR",
    NL: "EUR",
  };
  return marketCurrency[market.trim().toUpperCase()] ?? "USD";
}

type MarginParseResult =
  | { valid: true; value: string; display: string; converted: boolean }
  | { valid: false; message: string };

function parseMinimumMargin(raw: string): MarginParseResult {
  const input = raw.trim();
  if (!input) return { valid: false, message: "请填写最低毛利率。" };
  const hasPercent = /[%％]$/.test(input);
  const numericText = hasPercent ? input.slice(0, -1).trim() : input;
  const numericValue = Number(numericText);
  if (!numericText || !Number.isFinite(numericValue)) {
    return { valid: false, message: "最低毛利率格式不正确。" };
  }
  const decimalValue = hasPercent
    ? numericValue / 100
    : numericValue <= 1
      ? numericValue
      : numericValue / 100;
  if (decimalValue < 0 || decimalValue > 1) {
    return { valid: false, message: "最低毛利率必须在 0% 到 100% 之间。" };
  }
  const normalized = Math.round(decimalValue * 1_000_000) / 1_000_000;
  const percent = Math.round(normalized * 100_000) / 1_000;
  return {
    valid: true,
    value: String(normalized),
    display: `${percent}%`,
    converted: !hasPercent,
  };
}

function formatMinimumMargin(value: string | number) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return String(value);
  const percent = Math.round(numericValue * 100_000) / 1_000;
  return `${percent}%`;
}

function onMinimumMarginInput() {
  marginNotice.value = "";
  const result = parseMinimumMargin(minimumMarginInput.value);
  marginError.value = result.valid ? "" : result.message;
}

function commitMinimumMargin() {
  const result = parseMinimumMargin(minimumMarginInput.value);
  if (!result.valid) {
    marginError.value = result.message;
    marginNotice.value = "";
    return false;
  }
  marginError.value = "";
  marginNotice.value = result.converted ? `已按 ${result.display} 处理。` : "";
  minimumMarginInput.value = result.display;
  if (editable.value?.profit_constraints) {
    editable.value.profit_constraints.minimum_margin = result.value;
  }
  return true;
}

function toggleProfit() {
  if (!editable.value) return;
  editable.value.profit_constraints = profitEnabled.value ? defaultProfit() : null;
  minimumMarginInput.value = profitEnabled.value ? formatMinimumMargin("0.30") : "";
  marginError.value = "";
  marginNotice.value = "";
}

function submit() {
  if (profitEnabled.value && !commitMinimumMargin()) return;
  if (editable.value && canSubmit.value) emit("submit", cloneRequest(editable.value));
}

function invalid(field: string) {
  return props.fieldError === field || props.fieldError.endsWith(`.${field}`);
}
</script>

<template>
  <section class="analysis-card" aria-labelledby="analysis-title">
    <div class="section-heading">
      <div>
        <span class="eyebrow">01 · 定义机会</span>
        <h2 id="analysis-title">告诉 Agent 你想分析什么</h2>
      </div>
      <span class="dataset-pill">可选择数据来源</span>
    </div>

    <label class="field-label" for="market-query">商品与分析目标</label>
    <textarea
      id="market-query"
      class="query-input"
      :value="query"
      rows="4"
      placeholder="例如：分析便携咖啡机在美国亚马逊是否值得进入，目标毛利率至少 30%"
      :disabled="previewing || submitting"
      @input="emit('update:query', ($event.target as HTMLTextAreaElement).value)"
    ></textarea>
    <div class="query-footer">
      <span>支持中英文商品别名，先预解析再提交正式任务</span>
      <button
        class="primary-action"
        type="button"
        :disabled="query.trim().length < 5 || previewing || submitting"
        @click="emit('preview')"
      >
        {{ previewing ? "正在理解需求…" : preview ? "重新预解析" : "预解析需求" }}
      </button>
    </div>

    <template v-if="preview">
      <div class="preview-summary">
        <div>
          <span class="summary-label">识别置信度</span>
          <strong>{{ Math.round(preview.confidence * 100) }}%</strong>
        </div>
        <div>
          <span class="summary-label">数据可用性</span>
          <strong :class="selectedSource?.available ? 'text-success' : 'text-danger'">
            {{ selectedSource?.available ? "可分析" : "暂不可用" }}
          </strong>
        </div>
      </div>

      <div v-if="preview.missing_fields.length" class="notice danger" role="alert">
        <strong>还缺少必要信息</strong>
        <span>{{ preview.missing_fields.join("、") }}</span>
      </div>
      <div v-if="preview.ambiguities.length" class="notice warning" role="alert">
        <strong>需要确认</strong>
        <span>{{ preview.ambiguities.join("；") }}</span>
      </div>
      <div
        v-for="warning in visibleWarnings"
        :key="`${warning.code}-${warning.field}`"
        class="notice"
        :class="warning.severity"
        role="status"
      >
        <strong>{{ warning.code }}</strong><span>{{ warning.message }}</span>
      </div>

      <div v-if="editable" class="confirmation-panel">
        <div class="confirmation-title">
          <div>
            <span class="eyebrow">02 · 确认参数</span>
            <h3>检查 Agent 提取结果</h3>
          </div>
          <span>提交前可以直接修改</span>
        </div>

        <div class="form-grid">
          <label :class="{ invalid: invalid('market') }">
            <span>目标市场</span>
            <input
              v-model.trim="marketInput"
              list="market-choice-list"
              type="text"
              placeholder="例如：美国（US）"
              @change="commitMarket"
              @blur="commitMarket"
            />
            <datalist id="market-choice-list">
              <option
                v-for="choice in marketChoices"
                :key="choice.code"
                :value="choice.label"
              />
            </datalist>
            <small>可输入中文市场名称或两位市场代码</small>
          </label>
          <label
            class="source-selector"
            :class="{ invalid: invalid('platforms') || invalid('data_source_mode') }"
          >
            <span>分析平台与数据来源</span>
            <select v-model="selectedSourceKey">
              <option
                v-for="option in sourceOptions"
                :key="sourceKey(option)"
                :value="sourceKey(option)"
                :disabled="!option.available"
              >
                {{ option.label }}{{ option.available ? "" : `（${option.unavailable_reason}）` }}
              </option>
            </select>
            <small v-if="selectedSource">{{ sourceCapabilities(selectedSource) }}</small>
          </label>
          <label :class="{ invalid: invalid('category') }">
            <span>商品类目</span>
            <input v-model.trim="editable.category" type="text" @change="loadMetricCandidates" />
          </label>
          <label :class="{ invalid: invalid('keyword') }">
            <span>关键词</span>
            <input v-model.trim="editable.keyword" type="text" @change="loadMetricCandidates" />
          </label>
          <label :class="{ invalid: invalid('collection.product_limit') }">
            <span>商品数量</span>
            <input v-model.number="editable.collection.product_limit" min="1" max="50" type="number" />
          </label>
          <label :class="{ invalid: invalid('collection.review_limit_per_product') }">
            <span>每件商品评论数</span>
            <input
              v-model.number="editable.collection.review_limit_per_product"
              min="1"
              type="number"
            />
          </label>
        </div>

        <div v-if="selectedSource?.available" class="metric-batch-panel">
          <div>
            <span>宏观市场数据</span>
            <small>平台和市场必须一致，商品由标准别名或 LLM 判断；类目可以不同。</small>
          </div>
          <span v-if="metricBatchesLoading" class="metric-batch-state">正在读取可用批次…</span>
          <span v-else-if="metricBatchesError" class="metric-batch-state error" role="alert">
            {{ metricBatchesError }}
          </span>
          <template v-else>
            <select v-model="editable.market_metric_batch_id" aria-label="选择宏观市场数据批次">
              <option :value="null">不使用已上传的宏观市场数据</option>
              <option
                v-for="candidate in metricCandidates"
                :key="candidate.batch.id"
                :value="candidate.batch.id"
                :disabled="!candidateAccepted(candidate)"
              >
                {{ metricBatchLabel(candidate) }}
              </option>
            </select>
            <div v-if="selectedMetricBatch && selectedProductMatch" class="metric-batch-detail">
              <span>{{ metricSourceCopy[selectedMetricBatch.source_type] }} · 版本 {{ selectedMetricBatch.data_version }}</span>
              <span>数据截止 {{ shortDate(selectedMetricBatch.source_timestamp) }}</span>
              <strong class="match-success">
                {{ productMatchLabel(selectedProductMatch.decision) }} · 置信度 {{ Math.round(selectedProductMatch.confidence * 100) }}%
              </strong>
              <span>{{ selectedProductMatch.reason }}</span>
            </div>
            <details v-if="metricCandidates.length" class="match-results">
              <summary>查看 {{ metricCandidates.length }} 个批次的商品校验结果</summary>
              <ul>
                <li v-for="candidate in metricCandidates" :key="`match-${candidate.batch.id}`">
                  <div>
                    <b :class="candidate.product_match.decision">
                      {{ productMatchLabel(candidate.product_match.decision) }}
                    </b>
                    <span>{{ candidate.batch.keyword }} · {{ candidate.batch.category }}</span>
                  </div>
                  <p>{{ candidate.product_match.reason }}（{{ Math.round(candidate.product_match.confidence * 100) }}%）</p>
                </li>
              </ul>
            </details>
            <small v-if="!metricCandidates.some(candidateAccepted)" class="metric-batch-empty">
              当前平台和市场没有通过商品一致性校验的宏观数据，报告将使用可用的商品样本指标。
            </small>
          </template>
        </div>

        <label class="profit-toggle">
          <input v-model="profitEnabled" type="checkbox" @change="toggleProfit" />
          <span>
            <strong>同时测算利润可行性</strong>
            <small>不填写成本时仍可完成市场分析，不生成利润结论</small>
          </span>
        </label>

        <div v-if="profitEnabled && editable.profit_constraints" class="form-grid profit-grid">
          <label>
            <span>销售价格</span>
            <input v-model.trim="editable.profit_constraints.price" inputmode="decimal" />
          </label>
          <label>
            <span>商品成本</span>
            <input v-model.trim="editable.profit_constraints.product_cost" inputmode="decimal" />
          </label>
          <label>
            <span>平台费用</span>
            <input v-model.trim="editable.profit_constraints.platform_fee" inputmode="decimal" />
          </label>
          <label>
            <span>物流成本</span>
            <input v-model.trim="editable.profit_constraints.logistics_cost" inputmode="decimal" />
          </label>
          <label>
            <span>广告成本</span>
            <input v-model.trim="editable.profit_constraints.advertising_cost" inputmode="decimal" />
          </label>
          <label>
            <span>币种</span>
            <select v-model="editable.profit_constraints.currency">
              <option v-for="currency in currencyOptions" :key="currency.code" :value="currency.code">
                {{ currency.name }}（{{ currency.code }}）
              </option>
            </select>
          </label>
          <label :class="{ invalid: marginError }">
            <span>最低毛利率</span>
            <input
              v-model.trim="minimumMarginInput"
              inputmode="decimal"
              :aria-invalid="Boolean(marginError)"
              @input="onMinimumMarginInput"
              @blur="commitMinimumMargin"
            />
            <small v-if="marginError" class="field-feedback error" role="alert">{{ marginError }}</small>
            <small v-else-if="marginNotice" class="field-feedback success" role="status">{{ marginNotice }}</small>
          </label>
        </div>

        <div class="submit-row">
          <p v-if="!selectedSource?.available">
            当前没有可执行的数据来源，请选择已接入并获得授权的平台。
          </p>
          <p v-else>将使用 {{ selectedSource.label }}，提交后由 Worker 执行。</p>
          <button class="submit-action" type="button" :disabled="!canSubmit" @click="submit">
            {{ submitting ? "正在创建任务…" : "确认并开始分析" }}
          </button>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.analysis-card {
  padding: clamp(1.25rem, 2.5vw, 2rem);
  background: var(--cui-body-bg);
  border: 1px solid var(--cui-border-color);
  border-radius: 18px;
  box-shadow: 0 16px 40px rgb(25 36 61 / 7%);
}
.section-heading,
.confirmation-title,
.query-footer,
.submit-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.eyebrow {
  color: #5d6b82;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
h2 { margin: 0.35rem 0 1.5rem; font-size: clamp(1.35rem, 3vw, 1.8rem); }
h3 { margin: 0.25rem 0 0; font-size: 1.1rem; }
.dataset-pill {
  padding: 0.4rem 0.75rem;
  color: #285944;
  background: #e8f4ee;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
}
.field-label { display: block; margin-bottom: 0.5rem; font-weight: 700; }
.query-input {
  width: 100%;
  padding: 1rem;
  resize: vertical;
  color: var(--cui-body-color);
  background: var(--cui-tertiary-bg);
  border: 1px solid var(--cui-border-color);
  border-radius: 12px;
  line-height: 1.65;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.query-input:focus,
input:focus,
select:focus { border-color: #4f6bed; box-shadow: 0 0 0 3px rgb(79 107 237 / 14%); outline: 0; }
.query-footer { margin-top: 0.8rem; color: var(--cui-secondary-color); font-size: 0.78rem; }
.primary-action,
.submit-action {
  flex: 0 0 auto;
  padding: 0.72rem 1.15rem;
  color: white;
  background: #334bc4;
  border: 0;
  border-radius: 10px;
  font-weight: 750;
}
button:disabled { cursor: not-allowed; opacity: 0.55; }
.preview-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  margin-top: 1.5rem;
  overflow: hidden;
  background: var(--cui-border-color);
  border: 1px solid var(--cui-border-color);
  border-radius: 12px;
}
.preview-summary > div { display: flex; min-width: 0; padding: 0.9rem 1rem; background: var(--cui-body-bg); flex-direction: column; }
.summary-label { color: var(--cui-secondary-color); font-size: 0.72rem; }
.preview-summary strong { margin-top: 0.15rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.notice { display: flex; gap: 0.8rem; margin-top: 0.75rem; padding: 0.8rem 1rem; color: #24536a; background: #edf6fa; border-radius: 10px; font-size: 0.83rem; }
.notice.warning { color: #70571a; background: #fff6db; }
.notice.danger { color: #7c3131; background: #fcebea; }
.confirmation-panel { margin-top: 1.6rem; padding-top: 1.5rem; border-top: 1px solid var(--cui-border-color); }
.confirmation-title > span { color: var(--cui-secondary-color); font-size: 0.78rem; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin-top: 1.2rem; }
.form-grid label { display: flex; gap: 0.4rem; flex-direction: column; font-size: 0.78rem; font-weight: 700; }
.form-grid input,
.form-grid select { width: 100%; min-height: 42px; padding: 0.55rem 0.7rem; color: var(--cui-body-color); background: var(--cui-body-bg); border: 1px solid var(--cui-border-color); border-radius: 9px; }
.form-grid input:disabled { background: var(--cui-tertiary-bg); }
.form-grid label.invalid > span { color: #a33f48; }
.form-grid label.invalid input,
.form-grid label.invalid select { border-color: #c95862; box-shadow: 0 0 0 3px rgb(201 88 98 / 10%); }
.source-selector small { color: var(--cui-secondary-color); font-weight: 500; line-height: 1.45; }
.metric-batch-panel { display: grid; gap: 0.65rem; margin-top: 1rem; padding: 1rem; background: #f7f9fc; border: 1px solid #e1e6ef; border-radius: 12px; }
.metric-batch-panel > div:first-child { display: flex; justify-content: space-between; gap: 1rem; }
.metric-batch-panel > div:first-child > span { font-size: 0.8rem; font-weight: 750; }
.metric-batch-panel > div:first-child > small { color: var(--cui-secondary-color); font-size: 0.72rem; }
.metric-batch-panel select { width: 100%; min-height: 42px; padding: 0.55rem 0.7rem; color: var(--cui-body-color); background: var(--cui-body-bg); border: 1px solid var(--cui-border-color); border-radius: 9px; }
.metric-batch-detail { display: flex; flex-wrap: wrap; gap: 0.35rem 1rem; color: var(--cui-secondary-color); font-size: 0.7rem; }
.metric-batch-detail strong { width: 100%; color: #745b1b; font-weight: 650; }
.metric-batch-detail strong.match-success { color: #246247; }
.metric-batch-state, .metric-batch-empty { color: var(--cui-secondary-color); font-size: 0.75rem; }
.metric-batch-state.error { color: #9b3f48; }
.match-results summary { color: #526a9f; cursor: pointer; font-size: 0.72rem; font-weight: 700; }
.match-results ul { display: grid; gap: 0.45rem; margin: 0.6rem 0 0; padding: 0; list-style: none; }
.match-results li { padding: 0.6rem 0.7rem; background: var(--cui-body-bg); border: 1px solid var(--cui-border-color); border-radius: 8px; }
.match-results li > div { display: flex; align-items: center; gap: 0.55rem; }
.match-results b { padding: 0.15rem 0.35rem; color: #70571a; background: #fff1ca; border-radius: 4px; font-size: 0.62rem; }
.match-results b.same_product { color: #246247; background: #e2f3ea; }
.match-results b.different_product { color: #893e47; background: #fbe8ea; }
.match-results li span, .match-results p { color: var(--cui-secondary-color); font-size: 0.68rem; }
.match-results p { margin: 0.35rem 0 0; line-height: 1.45; }
.profit-toggle { display: flex; align-items: flex-start; gap: 0.75rem; margin-top: 1.3rem; padding: 1rem; cursor: pointer; background: var(--cui-tertiary-bg); border-radius: 12px; }
.profit-toggle input { width: 1.05rem; height: 1.05rem; margin-top: 0.2rem; accent-color: #334bc4; }
.profit-toggle span { display: flex; flex-direction: column; }
.profit-toggle small { margin-top: 0.2rem; color: var(--cui-secondary-color); }
.profit-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.field-feedback.error { color: #a33642; }
.field-feedback.success { color: #246247; }
.submit-row { margin-top: 1.5rem; }
.submit-row p { margin: 0; color: var(--cui-secondary-color); font-size: 0.8rem; }
.submit-action { padding-inline: 1.4rem; background: #18233f; }
@media (max-width: 767px) {
  .preview-summary,
  .form-grid,
  .profit-grid { grid-template-columns: 1fr; }
  .section-heading,
  .confirmation-title,
  .query-footer,
  .submit-row { align-items: stretch; flex-direction: column; }
  .metric-batch-panel > div:first-child { flex-direction: column; }
  .primary-action,
  .submit-action { width: 100%; }
}
</style>
