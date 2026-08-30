<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import type {
  CompetitorItem,
  EntryDecision,
  JsonValue,
  MarketMetric,
  MarketIntelligenceReport,
  ReviewTheme,
  Statement,
} from "../types/marketIntelligence";

const props = defineProps<{ report: MarketIntelligenceReport }>();
const emit = defineEmits<{
  evidence: [ids: string[], product?: CompetitorItem];
  metrics: [];
}>();

const statusCopy: Record<string, string> = {
  available: "可用", unavailable: "不可用", partial: "部分可用",
  stale: "数据过期", conflict: "数据冲突",
  COMPLETED: "完整报告", DEGRADED: "降级报告", FAILED: "生成失败",
};
const dataSourceCopy: Record<string, string> = {
  fixed_dataset: "固定数据集", official_api: "官方 API",
};
const metricCopy: Record<string, string> = {
  market_size: "市场规模", gmv: "商品交易总额（GMV）",
  sales_volume: "市场销售量", order_count: "市场订单量",
  active_product_count: "活跃商品数", active_brand_count: "活跃品牌数",
  category_traffic: "类目访问量", growth: "市场增长率",
  cagr: "复合年增长率", average_transaction_price: "平均成交价",
  gmv_market_share: "GMV 市场占比",
  price_distribution: "市场价格分布", brand_concentration: "品牌集中度",
  product_concentration: "商品集中度", sample_product_count: "数据集商品总数",
  sample_min_price: "样本最低价", sample_max_price: "样本最高价",
  sample_median_price: "样本价格中位数", sample_price_distribution: "样本价格分布",
  sample_sales_display_distribution: "样本销量展示分布",
  sample_shop_concentration: "样本店铺集中度",
  sample_product_concentration: "样本商品集中度",
  sample_rating_distribution: "样本评分分布",
  sample_review_count_distribution: "样本评论数分布",
  sample_review_activity: "样本评论活跃度",
  sample_brand_concentration: "样本品牌集中度",
};
const metricDescription: Record<string, string> = {
  market_size: "目标市场在当前统计范围内的整体规模。固定数据集缺少全市场汇总数据时，该指标会显示为暂不可用。",
  gmv: "目标市场在统计周期内的商品交易总额，用于判断市场容量。",
  sales_volume: "统计周期内目标市场产生的商品销售数量。",
  order_count: "统计周期内目标市场产生的有效订单数量。",
  active_product_count: "统计周期内产生销售、访问或其他有效经营活动的商品数量。",
  active_brand_count: "统计周期内产生销售、访问或其他有效经营活动的品牌数量。",
  category_traffic: "统计周期内目标类目获得的访问量，用于观察市场关注度和流量基础。",
  growth: "目标市场规模随时间的变化速度，用于判断市场处于增长、稳定或收缩阶段。",
  cagr: "根据多个年度统计周期计算的复合年增长率，用于观察市场的中长期增长趋势。",
  average_transaction_price: "由商品交易总额除以销售量计算，表示统计周期内每件商品的平均成交金额。",
  gmv_market_share: "商品交易总额占整体市场规模的比例，用于观察当前统计口径覆盖的市场份额。",
  price_distribution: "目标市场商品价格的整体分布情况，用于识别主流价格带。",
  brand_concentration: "头部品牌所占份额，用于判断市场是否已被少数品牌主导。",
  product_concentration: "头部商品所占份额，用于判断销量是否集中在少数爆款。",
  sample_product_count: "固定数据集中收录的商品总数，其中部分商品可能因价格等关键字段缺失而无法进入本次分析。",
  sample_min_price: "本次商品样本中观察到的最低价格。",
  sample_max_price: "本次商品样本中观察到的最高价格。",
  sample_median_price: "一半样本价格高于该值、一半低于该值，比平均价格更不容易受极端价格影响。",
  sample_price_distribution: "展示有价格数据的商品覆盖情况和价格区间，可用于识别样本中的主流定价水平。",
  sample_rating_distribution: "展示样本商品的评分覆盖情况及高低分布，用于快速判断用户对现有商品的整体满意度。",
  sample_review_count_distribution: "展示每个样本商品积累的评论数量。评论数可反映样本热度，不能直接视为销量。",
  sample_review_activity: "展示带日期评论的数量和时间跨度，用于观察评论活动；该指标不等同于市场增长率。",
  sample_brand_concentration: "展示样本是否集中在少数品牌。缺少可靠品牌字段时不计算该指标。",
  sample_sales_display_distribution: "展示样本商品可见销量的分布，用于比较商品热度层级。",
  sample_shop_concentration: "展示头部店铺在样本中的占比，用于判断店铺竞争集中程度。",
  sample_product_concentration: "展示头部商品在样本销量中的占比，用于判断爆款集中程度。",
};
const fieldCopy: Record<string, string> = {
  competitor_matrix: "竞品矩阵", market_snapshot: "市场快照",
  review_insights: "评论洞察", profit_analysis: "利润分析",
  entry_assessment: "市场进入判断", product_cost: "商品成本",
  platform_fee: "平台费用", logistics_cost: "物流成本",
  advertising_cost: "广告成本", observed_count: "观测数量",
  currency: "币种", binning_algorithm: "分箱方式", bins: "价格区间",
  lower: "下界", upper: "上界", upper_inclusive: "包含上界", count: "数量",
  sales_value_type: "销量值类型", sales_display: "销量展示值",
  product_count: "商品数", observed_product_count: "已观测商品数",
  total_product_count: "商品总数", coverage_ratio: "覆盖率",
  distinct_shop_count: "店铺数", top1_share: "头部第一名占比",
  top3_share: "头部前三名占比", top_shops: "头部店铺",
  shop_name: "店铺名称", exact_sales_product_count: "精确销量商品数",
  exact_sales_coverage_ratio: "精确销量覆盖率", exact_sales_total: "精确销量合计",
  top_products: "头部商品", product_id: "商品 ID", sales_value: "销量值", share: "占比",
  min: "最低值", max: "最高值", mean: "平均值", median: "中位数",
  total_review_count: "评论总数", dated_review_count: "带日期评论数",
  timestamp_coverage_ratio: "评论日期覆盖率", start_date: "最早评论日期",
  end_date: "最近评论日期", reviews_by_year: "各年份评论数",
};
const reasonCopy: Record<string, string> = {
  AGGREGATE_MARKET_DATA_MISSING: "缺少全市场汇总数据",
  MARKET_METRIC_INCOMPLETE: "市场指标不完整",
  REVIEW_DATA_INCOMPLETE: "评论数据不完整",
  COST_INPUT_UNAVAILABLE: "成本参数不完整",
  LLM_UNAVAILABLE: "报告合成服务不可用",
  PRODUCT_COLLECTION_PARTIAL: "商品样本采集不完整",
  BRAND_DATA_UNAVAILABLE: "商品样本缺少品牌信息",
  SELECTED_MARKET_METRIC_BATCH_INVALID: "所选宏观市场数据批次已失效或范围不匹配",
};
const sentimentCopy: Record<string, string> = {
  total_count: "评论总数",
  analyzed_count: "实际分析数",
  coverage_ratio: "分析覆盖率",
  positive_count: "正面评论数",
  positive_ratio: "正面占比",
  neutral_count: "中性评论数",
  neutral_ratio: "中性占比",
  negative_count: "负面评论数",
  negative_ratio: "负面占比",
};
const unitCopy: Record<string, string> = {
  count: "个", ratio: "%", percent: "%", percentage: "%", "%": "%",
  unit: "件", units: "件", product: "个商品", products: "个商品",
  brand: "个品牌", brands: "个品牌", order: "笔订单", orders: "笔订单",
  visit: "次访问", visits: "次访问", session: "次访问", sessions: "次访问",
  USD: "美元", CNY: "人民币", EUR: "欧元", GBP: "英镑", JPY: "日元",
  SEK: "瑞典克朗", CAD: "加元", AUD: "澳元",
};

const decisionCopy: Record<EntryDecision, { label: string; tone: string }> = {
  GO: { label: "建议进入", tone: "go" },
  CONDITIONAL_GO: { label: "有条件进入", tone: "conditional" },
  NO_GO: { label: "暂不进入", tone: "stop" },
  INSUFFICIENT_DATA: { label: "信息不足", tone: "limited" },
};
const decision = computed(() => decisionCopy[props.report.entry_assessment.decision]);
const visibleDataLimitations = computed(() =>
  props.report.data_limitations.filter(
    (item) => !/^market_snapshot\.[^.]+$/.test(item.field),
  ),
);
const visibleSnapshotMetrics = computed(() =>
  props.report.market_snapshot.metrics.filter(
    (metric) => metric.status !== "unavailable" && metric.value !== null,
  ),
);
const unavailableSnapshotMetrics = computed(() =>
  props.report.market_snapshot.metrics.filter(
    (metric) => metric.status === "unavailable" || metric.value === null,
  ),
);
const hasUnavailableMacroMetrics = computed(() =>
  unavailableSnapshotMetrics.value.some((metric) => !metric.metric_code.startsWith("sample_")),
);
const datasetProductCount = computed(() => {
  const metric = props.report.market_snapshot.metrics.find(
    (item) => item.metric_code === "sample_product_count",
  );
  return !metric || metric.value === null || typeof metric.value === "object"
    ? "暂无数据"
    : formatNumber(metric.value);
});
type CompetitorSortKey = "price" | "sales" | "rating";
type SortDirection = "asc" | "desc";
const competitorSortKey = ref<CompetitorSortKey | null>(null);
const competitorSortDirection = ref<SortDirection>("desc");
const openMetricHelp = ref<string | null>(null);
const themesExpanded = ref(false);
const concernsExpanded = ref(false);
const DEFAULT_THEME_COUNT = 5;

function groupReviewThemes(items: ReviewTheme[]) {
  const sorted = [...items].sort((left, right) =>
    right.mention_count - left.mention_count
    || Number(right.mention_ratio) - Number(left.mention_ratio)
    || left.theme.localeCompare(right.theme, "zh-CN"),
  );
  const frequent = sorted.filter((item) => item.mention_count > 1);
  return {
    primary: frequent.slice(0, DEFAULT_THEME_COUNT),
    hidden: [...frequent.slice(DEFAULT_THEME_COUNT), ...sorted.filter((item) => item.mention_count <= 1)],
  };
}

function hiddenThemeLabel(items: ReviewTheme[], noun: string) {
  const frequency = items.every((item) => item.mention_count <= 1) ? "低频" : "";
  return `查看另外 ${items.length} 个${frequency}${noun}`;
}

const reviewThemeGroups = computed(() => groupReviewThemes(props.report.review_insights.themes));
const concernThemeGroups = computed(() => groupReviewThemes([
  ...props.report.review_insights.pain_points,
  ...props.report.review_insights.unmet_needs,
]));
const visibleReviewThemes = computed(() => themesExpanded.value
  ? [...reviewThemeGroups.value.primary, ...reviewThemeGroups.value.hidden]
  : reviewThemeGroups.value.primary);
const visibleConcernThemes = computed(() => concernsExpanded.value
  ? [...concernThemeGroups.value.primary, ...concernThemeGroups.value.hidden]
  : concernThemeGroups.value.primary);
const sortedCompetitors = computed(() => {
  if (!competitorSortKey.value) return props.report.competitor_matrix;
  const key = competitorSortKey.value;
  const direction = competitorSortDirection.value;
  const numericValue = (item: MarketIntelligenceReport["competitor_matrix"][number]) => {
    if (key === "price") return Number(item.price);
    if (key === "sales") return item.sales_value;
    return item.rating === null ? null : Number(item.rating);
  };
  return [...props.report.competitor_matrix].sort((left, right) => {
    const leftValue = numericValue(left);
    const rightValue = numericValue(right);
    if (leftValue === null && rightValue === null) return left.rank - right.rank;
    if (leftValue === null) return 1;
    if (rightValue === null) return -1;
    const difference = leftValue - rightValue;
    if (difference === 0) return left.rank - right.rank;
    return direction === "asc" ? difference : -difference;
  });
});
const statementGroups = computed<
  { title: string; kind: "fact" | "inference" | "opportunity" | "risk" | "action"; items: Statement[] }[]
>(() => [
  { title: "事实", kind: "fact", items: props.report.facts },
  { title: "推断", kind: "inference", items: props.report.inferences },
  { title: "市场机会", kind: "opportunity", items: props.report.opportunity_signals },
  { title: "风险", kind: "risk", items: props.report.risk_signals },
  { title: "后续动作", kind: "action", items: props.report.suggested_actions },
]);

function dateTime(value: string | null) {
  if (!value) return "当前数据无法提供";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function valueText(metric: MarketMetric) {
  const { value, unit, status } = metric;
  if (status === "unavailable" || value === null) return "当前数据无法提供";
  const raw = typeof value === "object" ? JSON.stringify(localizeJson(value)) : formatNumber(value);
  if (!unit || typeof value === "object") return raw;
  if (unit === "ratio") return percent(value as string | number);
  if (["percent", "percentage", "%"].includes(unit)) return `${raw}%`;
  return `${raw} ${localizedUnit(unit)}`;
}

function localizedUnit(unit: string) {
  return unitCopy[unit] || unitCopy[unit.toUpperCase()] || unitCopy[unit.toLowerCase()] || unit;
}

function formatNumber(value: JsonValue) {
  const numeric = typeof value === "number" || typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(numeric) ? numeric.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) : String(value);
}

function structuredMetric(value: JsonValue): value is Record<string, JsonValue> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function metricExplanation(metric: MarketMetric) {
  return metricDescription[metric.metric_code] || metric.methodology || "展示当前样本中该指标的统计结果。";
}

function metricWarning(metric: MarketMetric) {
  if (metric.status === "unavailable") return "数据限制：当前数据源缺少计算该指标所需的信息。";
  if (metric.metric_code === "sample_review_count_distribution") {
    return "解读提示：评论数反映样本热度，不能直接视为销量。";
  }
  if (metric.metric_code === "sample_review_activity") {
    return "解读提示：评论活动反映用户反馈活跃程度，不代表市场增长率。";
  }
  if (metric.status === "partial" && structuredMetric(metric.value)) {
    const observed = metric.value.observed_count ?? metric.value.observed_product_count;
    const total = metric.value.total_product_count;
    if (observed !== undefined && total !== undefined) {
      return `覆盖提示：当前覆盖 ${formatNumber(observed)}/${formatNumber(total)} 个样本商品。`;
    }
    return "覆盖提示：该指标仅使用部分样本数据，请结合覆盖率解读。";
  }
  return null;
}

function unavailableMetricReason(metric: MarketMetric) {
  return copy(metric.reason_code || "MARKET_METRIC_INCOMPLETE", reasonCopy);
}

function toggleMetricHelp(metricCode: string) {
  openMetricHelp.value = openMetricHelp.value === metricCode ? null : metricCode;
}

function closeMetricHelp() {
  openMetricHelp.value = null;
}

onMounted(() => document.addEventListener("click", closeMetricHelp));
onBeforeUnmount(() => document.removeEventListener("click", closeMetricHelp));

function formatMetricField(metric: MarketMetric, key: string, value: JsonValue) {
  if (value === null) return "暂无数据";
  if (key.endsWith("ratio") || key.endsWith("share")) return percent(value as string | number);
  if (key === "currency" && typeof value === "string") return localizedUnit(value);
  if (key === "start_date" || key === "end_date") {
    const date = new Date(String(value));
    return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat("zh-CN").format(date);
  }
  if (key === "reviews_by_year" && structuredMetric(value)) {
    return Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([year, count]) => `${year} 年 ${formatNumber(count)} 条`)
      .join(" · ");
  }
  if (Array.isArray(value) || structuredMetric(value)) return JSON.stringify(localizeJson(value));

  const formatted = formatNumber(value);
  if (["observed_count", "observed_product_count", "total_product_count", "product_count"].includes(key)) {
    return `${formatted} 个商品`;
  }
  if (["total_review_count", "dated_review_count"].includes(key)) return `${formatted} 条`;
  if (["min", "max", "mean", "median"].includes(key)) {
    if (metric.metric_code.includes("price")) {
      return metric.unit ? `${formatted} ${localizedUnit(metric.unit)}` : formatted;
    }
    if (metric.metric_code.includes("rating")) return `${formatted} 分`;
    if (metric.metric_code.includes("review_count")) return `${formatted} 条`;
  }
  return formatted;
}

function yearlyReviewEntries(value: JsonValue) {
  if (!structuredMetric(value)) return [];
  return Object.entries(value).sort(([left], [right]) => left.localeCompare(right));
}

function copy(value: string, labels: Record<string, string>) {
  return labels[value] || value.replaceAll("_", " ");
}

function reviewSummary(value: string) {
  const match = value.match(/^(.+) (appears|is reported|is requested) in (\d+) of (\d+) reviews\.$/);
  if (!match) return value;
  const [, label, verb, count, total] = match;
  if (verb === "is reported") return `${total} 条评论中有 ${count} 条提到“${label}”问题。`;
  if (verb === "is requested") return `${total} 条评论中有 ${count} 条表达了“${label}”需求。`;
  return `“${label}”在 ${total} 条评论中出现 ${count} 次。`;
}

function fieldLabel(value: string) {
  const leaf = value.split(".").at(-1) || value;
  return copy(leaf, { ...metricCopy, ...fieldCopy });
}

function localizeJson(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(localizeJson);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [fieldLabel(key), localizeJson(item)]),
    ) as Record<string, JsonValue>;
  }
  if (typeof value === "string") {
    return {
      four_equal_width_bins: "四个等宽区间", exact: "精确值",
      lower_bound: "下限值", range: "区间值", unknown: "未知",
    }[value] || value;
  }
  return value;
}

function decimal(value: string | null, suffix = "") {
  return value === null ? "当前数据无法提供" : `${value}${suffix}`;
}

function percent(value: string | number | undefined) {
  if (value === undefined) return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(1)}%` : String(value);
}

function sentimentValue(label: string, value: string | number) {
  if (label.endsWith("_ratio")) return percent(value);
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toLocaleString("zh-CN")} 条` : String(value);
}

function evidence(ids: string[], product?: CompetitorItem) {
  if (ids.length) emit("evidence", ids, product);
}

function statementTone(kind: "fact" | "inference" | "opportunity" | "risk" | "action") {
  return `statement-${kind}`;
}

function toggleCompetitorSort(key: CompetitorSortKey) {
  if (competitorSortKey.value === key) {
    competitorSortDirection.value = competitorSortDirection.value === "desc" ? "asc" : "desc";
    return;
  }
  competitorSortKey.value = key;
  competitorSortDirection.value = "desc";
}

function competitorAriaSort(key: CompetitorSortKey) {
  if (competitorSortKey.value !== key) return "none";
  return competitorSortDirection.value === "asc" ? "ascending" : "descending";
}
</script>

<template>
  <section class="report-shell" aria-labelledby="report-title">
    <header class="report-hero">
      <div>
        <span class="eyebrow">市场情报 · {{ copy(report.status, statusCopy) }}</span>
        <h2 id="report-title">{{ report.scope.keyword }} 市场机会报告</h2>
        <p>
          {{ report.scope.platforms.join(" / ") }} · {{ report.scope.market }} ·
          {{ report.scope.category }}
        </p>
      </div>
      <div class="report-meta">
        <span>报告 #{{ report.report_id.slice(0, 8) }}</span>
        <strong>{{ dateTime(report.generated_at) }}</strong>
      </div>
    </header>

    <div class="scope-strip">
      <div><span>数据集商品总数</span><strong>{{ datasetProductCount }}</strong></div>
      <div><span>评论样本</span><strong>{{ report.scope.actual_review_count }}</strong></div>
      <div><span>数据模式</span><strong>{{ copy(report.scope.data_source_mode, dataSourceCopy) }}</strong></div>
      <div><span>数据截止</span><strong>{{ dateTime(report.scope.end_time) }}</strong></div>
    </div>

    <section v-if="visibleDataLimitations.length" class="limitations" aria-labelledby="limitations-title">
      <div class="section-title">
        <div><span>优先阅读</span><h3 id="limitations-title">数据限制</h3></div>
        <b>{{ visibleDataLimitations.length }} 项影响</b>
      </div>
      <div class="limitation-grid">
        <article v-for="item in visibleDataLimitations" :key="item.limitation_id">
          <div><span>{{ copy(item.status, statusCopy) }}</span><code>{{ fieldLabel(item.field) }}</code></div>
          <h4>{{ item.message }}</h4>
          <p>原因：{{ copy(item.reason_code, reasonCopy) }}</p>
          <button v-if="item.evidence_ids.length" type="button" @click="evidence(item.evidence_ids)">
            查看相关证据
          </button>
        </article>
      </div>
    </section>

    <section class="report-section" aria-labelledby="snapshot-title">
      <div class="section-title">
        <div><span>01</span><h3 id="snapshot-title">市场快照</h3></div>
        <b>{{ copy(report.market_snapshot.status, statusCopy) }}</b>
      </div>
      <div v-if="visibleSnapshotMetrics.length" class="metric-grid">
        <article
          v-for="metric in visibleSnapshotMetrics"
          :key="metric.metric_code"
          class="metric-card"
        >
          <div class="metric-heading">
            <div class="metric-title">
              <span>{{ copy(metric.metric_code, metricCopy) }}</span>
              <div
                class="metric-help"
                :class="{ open: openMetricHelp === metric.metric_code }"
                @click.stop
              >
                <button
                  type="button"
                  class="metric-help-button"
                  :aria-label="`查看${copy(metric.metric_code, metricCopy)}说明`"
                  :aria-expanded="openMetricHelp === metric.metric_code"
                  :aria-controls="`metric-help-${metric.metric_code}`"
                  @click="toggleMetricHelp(metric.metric_code)"
                  @keydown.esc="closeMetricHelp"
                >
                  <span aria-hidden="true">i</span>
                </button>
                <div
                  :id="`metric-help-${metric.metric_code}`"
                  class="metric-tooltip"
                  role="tooltip"
                >
                  {{ metricExplanation(metric) }}
                </div>
              </div>
            </div>
            <em>{{ copy(metric.status, statusCopy) }}</em>
          </div>
          <strong v-if="metric.status === 'unavailable' || metric.value === null">当前数据无法提供</strong>
          <dl v-else-if="structuredMetric(metric.value)" class="metric-details">
            <div
              v-for="(value, key) in metric.value"
              :key="key"
              :class="{ 'metric-detail-wide': key === 'reviews_by_year' }"
            >
              <dt>{{ fieldLabel(key) }}</dt>
              <dd v-if="key === 'reviews_by_year'" class="year-review-list">
                <span v-for="([year, count]) in yearlyReviewEntries(value)" :key="year">
                  {{ year }} 年 <b>{{ formatNumber(count) }}</b> 条
                </span>
              </dd>
              <dd v-else>{{ formatMetricField(metric, key, value) }}</dd>
            </div>
          </dl>
          <strong v-else>{{ valueText(metric) }}</strong>
          <small v-if="metricWarning(metric)" class="metric-warning">{{ metricWarning(metric) }}</small>
          <button
            v-if="metric.evidence_ids.length"
            class="metric-evidence"
            type="button"
            @click="evidence(metric.evidence_ids)"
          >
            查看 {{ metric.evidence_ids.length }} 条证据 →
          </button>
        </article>
      </div>
      <p v-else-if="!unavailableSnapshotMetrics.length" class="unavailable">当前数据无法提供市场指标。</p>
      <details v-if="unavailableSnapshotMetrics.length" class="unavailable-metrics">
        <summary>
          <span>
            <strong>{{ unavailableSnapshotMetrics.length }} 项市场指标暂无数据</strong>
            <small>已收起，不影响查看其他可用结果</small>
          </span>
          <b>展开查看</b>
        </summary>
        <div class="unavailable-metric-list">
          <div v-for="metric in unavailableSnapshotMetrics" :key="`unavailable-${metric.metric_code}`">
            <strong>{{ copy(metric.metric_code, metricCopy) }}</strong>
            <span>{{ unavailableMetricReason(metric) }}</span>
          </div>
        </div>
        <button
          v-if="hasUnavailableMacroMetrics"
          class="manage-metrics-link"
          type="button"
          @click="emit('metrics')"
        >
          上传宏观市场数据 →
        </button>
      </details>
    </section>

    <section class="report-section" aria-labelledby="competitor-title">
      <div class="section-title">
        <div><span>02</span><h3 id="competitor-title">竞品矩阵</h3></div>
        <b>{{ report.competitor_matrix.length }} 个商品</b>
      </div>
      <div v-if="report.competitor_matrix.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>排名 / 商品</th>
              <th>品牌</th>
              <th :aria-sort="competitorAriaSort('price')">
                <button class="sort-button" type="button" aria-label="按价格排序" @click="toggleCompetitorSort('price')">
                  价格<span class="sort-arrows" aria-hidden="true"><i :class="{ active: competitorSortKey === 'price' && competitorSortDirection === 'asc' }">▲</i><i :class="{ active: competitorSortKey === 'price' && competitorSortDirection === 'desc' }">▼</i></span>
                </button>
              </th>
              <th :aria-sort="competitorAriaSort('sales')">
                <button class="sort-button" type="button" aria-label="按销量排序" @click="toggleCompetitorSort('sales')">
                  销量<span class="sort-arrows" aria-hidden="true"><i :class="{ active: competitorSortKey === 'sales' && competitorSortDirection === 'asc' }">▲</i><i :class="{ active: competitorSortKey === 'sales' && competitorSortDirection === 'desc' }">▼</i></span>
                </button>
              </th>
              <th :aria-sort="competitorAriaSort('rating')">
                <button class="sort-button" type="button" aria-label="按评分排序" @click="toggleCompetitorSort('rating')">
                  评分<span class="sort-arrows" aria-hidden="true"><i :class="{ active: competitorSortKey === 'rating' && competitorSortDirection === 'asc' }">▲</i><i :class="{ active: competitorSortKey === 'rating' && competitorSortDirection === 'desc' }">▼</i></span>
                </button>
              </th>
              <th>评论</th>
              <th>证据</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in sortedCompetitors" :key="item.product_id">
              <td><b>#{{ item.rank }}</b><div>{{ item.title }}</div><small>{{ item.product_id }}</small></td>
              <td>{{ item.brand || "—" }}</td>
              <td>{{ item.currency }} {{ item.price }}</td>
              <td>{{ item.sales_display ?? item.sales_value ?? "当前数据无法提供" }}</td>
              <td>{{ item.rating || "—" }}</td>
              <td>{{ item.review_count ?? "—" }}</td>
              <td><button type="button" @click="evidence(item.evidence_ids, item)">查看</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="unavailable">当前数据无法提供竞品样本。</p>
    </section>

    <div class="two-column">
      <section class="report-section" aria-labelledby="reviews-title">
        <div class="section-title">
          <div><span>03</span><h3 id="reviews-title">评论洞察</h3></div>
          <b>{{ copy(report.review_insights.status, statusCopy) }}</b>
        </div>
        <template v-if="report.review_insights.status !== 'unavailable'">
          <div class="sentiment-row">
            <div v-for="(value, label) in report.review_insights.sentiment_distribution" :key="label">
              <span>{{ copy(label, sentimentCopy) }}</span><strong>{{ sentimentValue(label, value) }}</strong>
            </div>
          </div>
          <div class="theme-group">
            <h4>主要主题</h4>
            <p v-if="!visibleReviewThemes.length && reviewThemeGroups.hidden.length" class="theme-collapsed-hint">
              当前主题均为单次反馈，可按需展开查看。
            </p>
            <button
              v-for="theme in visibleReviewThemes"
              :key="theme.theme"
              type="button"
              :class="{ 'low-frequency-theme': theme.mention_count <= 1 }"
              @click="evidence(theme.evidence_ids)"
            >
              <span>{{ theme.theme }}</span><b>{{ theme.mention_count }} 次 · {{ percent(theme.mention_ratio) }}</b><small>{{ reviewSummary(theme.summary) }}</small>
            </button>
            <button
              v-if="reviewThemeGroups.hidden.length"
              type="button"
              class="theme-toggle"
              :aria-expanded="themesExpanded"
              @click="themesExpanded = !themesExpanded"
            >
              {{ themesExpanded ? "收起其余主题" : hiddenThemeLabel(reviewThemeGroups.hidden, "主题") }}
              <span aria-hidden="true">{{ themesExpanded ? "▲" : "▼" }}</span>
            </button>
          </div>
          <div class="theme-group danger-themes">
            <h4>痛点与未满足需求</h4>
            <p v-if="!visibleConcernThemes.length && concernThemeGroups.hidden.length" class="theme-collapsed-hint">
              当前反馈均只出现一次，可按需展开查看。
            </p>
            <button
              v-for="theme in visibleConcernThemes"
              :key="`${theme.theme}-${theme.summary}`"
              type="button"
              :class="{ 'low-frequency-theme': theme.mention_count <= 1 }"
              @click="evidence(theme.evidence_ids)"
            >
              <span>{{ theme.theme }}</span><b>{{ theme.mention_count }} 次 · {{ percent(theme.mention_ratio) }}</b><small>{{ reviewSummary(theme.summary) }}</small>
            </button>
            <button
              v-if="concernThemeGroups.hidden.length"
              type="button"
              class="theme-toggle"
              :aria-expanded="concernsExpanded"
              @click="concernsExpanded = !concernsExpanded"
            >
              {{ concernsExpanded ? "收起其余反馈" : hiddenThemeLabel(concernThemeGroups.hidden, "反馈") }}
              <span aria-hidden="true">{{ concernsExpanded ? "▲" : "▼" }}</span>
            </button>
          </div>
        </template>
        <p v-else class="unavailable">当前数据无法提供评论洞察。</p>
      </section>

      <section class="report-section" aria-labelledby="profit-title">
        <div class="section-title">
          <div><span>04</span><h3 id="profit-title">利润分析</h3></div>
          <b>{{ copy(report.profit_analysis.status, statusCopy) }}</b>
        </div>
        <template v-if="report.profit_analysis.status === 'available'">
          <div class="profit-summary">
            <div><span>预计利润</span><strong>{{ report.profit_analysis.currency }} {{ decimal(report.profit_analysis.profit) }}</strong></div>
            <div><span>预计毛利率</span><strong>{{ percent(report.profit_analysis.margin ?? undefined) }}</strong></div>
            <div><span>最低毛利要求</span><strong>{{ percent(report.profit_analysis.minimum_margin ?? undefined) }}</strong></div>
          </div>
          <div class="profit-verdict" :class="report.profit_analysis.meets_minimum_margin ? 'pass' : 'fail'">
            {{ report.profit_analysis.meets_minimum_margin ? "达到目标毛利要求" : "未达到目标毛利要求" }}
          </div>
          <dl class="breakdown">
            <div v-for="(value, label) in report.profit_analysis.breakdown" :key="label">
              <dt>{{ copy(label, fieldCopy) }}</dt><dd>{{ value }}</dd>
            </div>
          </dl>
          <button class="evidence-link" type="button" @click="evidence(report.profit_analysis.evidence_ids)">查看计算依据 →</button>
        </template>
        <p v-else class="unavailable">当前数据无法提供利润测算，请补充售价与完整成本。</p>
      </section>
    </div>

    <section class="decision-card" :class="decision.tone" aria-labelledby="decision-title">
      <div><span>05 · 进入判断</span><h3 id="decision-title">{{ decision.label }}</h3></div>
      <p>{{ report.entry_assessment.summary }}</p>
      <button type="button" @click="evidence(report.entry_assessment.evidence_ids)">查看判断证据</button>
    </section>

    <section class="report-section statements" aria-labelledby="conclusions-title">
      <div class="section-title"><div><span>06</span><h3 id="conclusions-title">结论与行动</h3></div></div>
      <div class="statement-columns">
        <div v-for="group in statementGroups" :key="group.title" class="statement-group">
          <h4>{{ group.title }} <span>{{ group.items.length }}</span></h4>
          <article v-for="item in group.items" :key="item.statement_id" :class="statementTone(group.kind)">
            <p>{{ item.text }}</p>
            <footer>
              <span>置信度 {{ Math.round(item.confidence * 100) }}%</span>
              <button v-if="item.evidence_ids.length" type="button" @click="evidence(item.evidence_ids)">证据 →</button>
            </footer>
          </article>
          <p v-if="!group.items.length" class="empty-group">暂无内容</p>
        </div>
      </div>
    </section>

    <footer class="report-footer">
      <span>共 {{ report.evidence_refs.length }} 条证据来源</span>
      <button type="button" @click="evidence(report.evidence_refs.map((item) => item.evidence_id))">
        查看全部证据
      </button>
    </footer>
  </section>
</template>

<style scoped>
.report-shell { margin-top: 1.5rem; color: #243047; }
.report-hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; padding: clamp(1.4rem, 3vw, 2.2rem); color: #f7f9ff; background: linear-gradient(125deg, #17233e, #273f6d 72%, #315a70); border-radius: 18px 18px 0 0; }
.eyebrow { color: #a4b7dd; font-size: 0.7rem; font-weight: 800; letter-spacing: 0.11em; text-transform: uppercase; }
.report-hero h2 { margin: 0.4rem 0; color: white; font-size: clamp(1.45rem, 3vw, 2.1rem); }
.report-hero p { margin: 0; color: #b7c6e1; }
.report-meta { display: flex; align-items: flex-end; color: #98a9c9; flex-direction: column; font-size: 0.67rem; }
.report-meta strong { margin-top: 0.25rem; color: #e4eafb; font-size: 0.75rem; }
.scope-strip { display: grid; grid-template-columns: repeat(4, 1fr); overflow: hidden; background: #fff; border: 1px solid #e0e5ed; border-top: 0; border-radius: 0 0 18px 18px; }
.scope-strip div { display: flex; min-width: 0; padding: 1rem; border-right: 1px solid #e7ebf1; flex-direction: column; }
.scope-strip div:last-child { border: 0; }
.scope-strip span { color: #7d889c; font-size: 0.67rem; }
.scope-strip strong { margin-top: 0.2rem; overflow: hidden; font-size: 0.82rem; text-overflow: ellipsis; white-space: nowrap; }
.limitations,
.report-section { margin-top: 1rem; padding: clamp(1.1rem, 2vw, 1.5rem); background: #fff; border: 1px solid #e0e5ed; border-radius: 16px; }
.limitations { color: #5a4516; background: #fffaf0; border-color: #efdfa9; }
.section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
.section-title > div { display: flex; align-items: baseline; gap: 0.65rem; }
.section-title span { color: #8a96aa; font-size: 0.7rem; font-weight: 800; }
.section-title h3 { margin: 0; font-size: 1.05rem; }
.section-title b { padding: 0.25rem 0.5rem; color: #66758e; background: #f0f3f7; border-radius: 5px; font-size: 0.65rem; text-transform: uppercase; }
.limitation-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; }
.limitation-grid article { padding: 0.9rem; background: rgb(255 255 255 / 65%); border: 1px solid #efdfa9; border-radius: 10px; }
.limitation-grid article > div { display: flex; justify-content: space-between; color: #8a6a20; font-size: 0.65rem; text-transform: uppercase; }
.limitation-grid h4 { margin: 0.55rem 0 0.25rem; font-size: 0.84rem; }
.limitation-grid p { margin: 0; color: #897441; font-size: 0.7rem; }
button { color: #3655b3; background: transparent; border: 0; font-weight: 700; }
.limitation-grid button { margin-top: 0.6rem; padding: 0; color: #745917; font-size: 0.68rem; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); align-items: stretch; gap: 0.75rem; }
.metric-card { display: flex; box-sizing: border-box; min-width: 0; max-width: 100%; min-height: 150px; padding: 1rem; color: inherit; text-align: left; background: #f7f9fc; border: 1px solid #e5e9f0; border-radius: 11px; flex-direction: column; }
.metric-card > * { min-width: 0; max-width: 100%; overflow-wrap: anywhere; word-break: break-word; }
.metric-heading { position: relative; display: flex; align-items: flex-start; justify-content: space-between; gap: 0.5rem; }
.metric-title { display: flex; min-width: 0; align-items: center; gap: 0.35rem; }
.metric-card span { color: #5f6d84; font-size: 0.76rem; font-weight: 800; }
.metric-heading em { flex: 0 0 auto; padding: 0.18rem 0.38rem; color: #687890; background: #e8edf5; border-radius: 4px; font-size: 0.58rem; font-style: normal; font-weight: 700; }
.metric-help { flex: 0 0 auto; }
.metric-help-button { display: inline-grid; width: 1rem; height: 1rem; padding: 0; place-items: center; color: #65748c; background: #e4e9f1; border: 1px solid #cbd3df; border-radius: 50%; cursor: help; }
.metric-help-button span { color: inherit; font-family: Georgia, serif; font-size: 0.68rem; line-height: 1; text-transform: none; }
.metric-help-button:hover,
.metric-help-button:focus-visible { color: #fff; background: #405fb5; border-color: #405fb5; outline: none; }
.metric-help-button:focus-visible { box-shadow: 0 0 0 3px rgb(64 95 181 / 20%); }
.metric-tooltip { position: absolute; z-index: 5; top: calc(100% + 0.45rem); right: 0; left: 0; visibility: hidden; padding: 0.7rem 0.75rem; color: #f7f9ff; background: #263650; border-radius: 8px; box-shadow: 0 8px 22px rgb(31 44 68 / 24%); opacity: 0; font-size: 0.7rem; font-weight: 500; line-height: 1.55; pointer-events: none; transform: translateY(-4px); transition: opacity 0.15s ease, transform 0.15s ease, visibility 0.15s; }
.metric-help:hover .metric-tooltip,
.metric-help:focus-within .metric-tooltip,
.metric-help.open .metric-tooltip { visibility: visible; opacity: 1; transform: translateY(0); }
.metric-card strong { margin: 0.45rem 0; color: #18233c; font-size: 1.15rem; white-space: normal; }
.metric-details { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.45rem; margin: 0.65rem 0; }
.metric-details div { min-width: 0; padding: 0.5rem; background: #eef2f8; border-radius: 7px; }
.metric-details div:last-child:nth-child(odd) { grid-column: 1 / -1; }
.metric-details div.metric-detail-wide { grid-column: 1 / -1; }
.metric-details dt { color: #7a8699; font-size: 0.6rem; font-weight: 500; }
.metric-details dd { margin: 0.15rem 0 0; overflow-wrap: anywhere; color: #22304a; font-size: 0.72rem; font-weight: 750; line-height: 1.4; }
.year-review-list { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.year-review-list span { padding: 0.22rem 0.42rem; color: #526079; background: #fff; border: 1px solid #dce2eb; border-radius: 5px; font-size: 0.65rem; font-weight: 500; white-space: nowrap; }
.year-review-list b { color: #263a63; }
.metric-warning { margin-top: 0.15rem; padding: 0.5rem 0.6rem; color: #795c1d; background: #fff5d9; border-radius: 6px; font-size: 0.65rem; font-weight: 500; line-height: 1.45; }
.metric-evidence { align-self: flex-start; margin-top: auto; padding: 0.7rem 0 0; color: #4664bc; font-size: 0.65rem; cursor: pointer; }
.metric-evidence:focus-visible { outline: 2px solid #4664bc; outline-offset: 3px; border-radius: 3px; }
.unavailable-metrics { margin-top: 0.85rem; overflow: hidden; background: #f7f8fa; border: 1px solid #e5e8ee; border-radius: 10px; }
.unavailable-metrics summary { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.85rem 1rem; color: #68758a; cursor: pointer; list-style: none; }
.unavailable-metrics summary::-webkit-details-marker { display: none; }
.unavailable-metrics summary span { display: flex; min-width: 0; flex-direction: column; }
.unavailable-metrics summary strong { color: #4c596f; font-size: 0.76rem; }
.unavailable-metrics summary small { margin-top: 0.15rem; font-size: 0.65rem; }
.unavailable-metrics summary > b { flex: 0 0 auto; color: #5c70a8; font-size: 0.66rem; }
.unavailable-metrics[open] summary { border-bottom: 1px solid #e5e8ee; }
.unavailable-metrics[open] summary > b { font-size: 0; }
.unavailable-metrics[open] summary > b::after { font-size: 0.66rem; content: "收起"; }
.unavailable-metric-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.5rem; padding: 0.8rem 1rem; }
.unavailable-metric-list div { display: flex; min-width: 0; justify-content: space-between; gap: 0.75rem; padding: 0.55rem 0.65rem; background: #fff; border-radius: 7px; }
.unavailable-metric-list strong { color: #3d4a60; font-size: 0.7rem; }
.unavailable-metric-list span { color: #8791a2; font-size: 0.65rem; text-align: right; }
.manage-metrics-link { margin: 0 1rem 0.9rem; padding: 0.5rem 0.7rem; color: #405da9; background: #fff; border: 1px solid #cbd5ed; border-radius: 7px; font-size: 0.68rem; font-weight: 750; }
.manage-metrics-link:hover { background: #f1f4fb; border-color: #9eafd5; }
.manage-metrics-link:focus-visible { outline: 2px solid #4664bc; outline-offset: 2px; }
.table-wrap { overflow: auto; }
table { width: 100%; min-width: 820px; border-collapse: collapse; font-size: 0.75rem; }
th { padding: 0.65rem; color: #7e899c; background: #f5f7fa; text-align: left; font-size: 0.66rem; }
.sort-button { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0; color: inherit; font: inherit; white-space: nowrap; }
.sort-button:focus-visible { outline: 2px solid #4664bc; outline-offset: 3px; border-radius: 3px; }
.sort-arrows { display: inline-flex; color: #b3bbc9; flex-direction: column; font-size: 0.48rem; line-height: 0.72; }
.sort-arrows i { font-style: normal; transition: color 0.15s ease; }
.sort-arrows i.active { color: #3655b3; }
.sort-button:hover .sort-arrows i { color: #7183b6; }
.sort-button:hover .sort-arrows i.active { color: #28469f; }
td { padding: 0.75rem 0.65rem; border-bottom: 1px solid #edf0f4; }
td:first-child { max-width: 300px; }
td:first-child b { float: left; margin-right: 0.5rem; color: #415bb0; }
td:first-child div { font-weight: 650; }
td small { color: #929cad; }
.two-column { display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 1rem; }
.sentiment-row,
.profit-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.6rem; }
.sentiment-row div,
.profit-summary div { display: flex; padding: 0.75rem; background: #f6f8fb; border-radius: 9px; flex-direction: column; }
.sentiment-row span,
.profit-summary span { color: #7e899c; font-size: 0.66rem; }
.sentiment-row strong,
.profit-summary strong { margin-top: 0.2rem; font-size: 0.9rem; }
.theme-group { margin-top: 1rem; }
.theme-group h4 { margin-bottom: 0.5rem; font-size: 0.78rem; }
.theme-group button { display: grid; width: 100%; grid-template-columns: 1fr auto; gap: 0.2rem 0.5rem; margin-top: 0.4rem; padding: 0.7rem; color: #263249; text-align: left; background: #f5f8fc; border-radius: 8px; }
.theme-group button b { color: #4964b5; font-size: 0.67rem; }
.theme-group button small { grid-column: 1 / -1; color: #7b879b; font-weight: 400; }
.theme-group button:focus-visible { outline: 2px solid #4664bc; outline-offset: 2px; }
.theme-group button.low-frequency-theme { opacity: 0.86; }
.theme-collapsed-hint { margin: 0.4rem 0 0; padding: 0.65rem 0.75rem; color: #7b879b; background: #f7f8fa; border-radius: 8px; font-size: 0.68rem; }
.theme-group button.theme-toggle { display: flex; align-items: center; justify-content: center; gap: 0.4rem; color: #4964b5; background: transparent; border: 1px dashed #bdc8e2; font-size: 0.68rem; font-weight: 700; text-align: center; }
.theme-group button.theme-toggle:hover { background: #f3f6fc; border-color: #8fa0cb; }
.theme-group button.theme-toggle span { font-size: 0.55rem; }
.danger-themes button { background: #fff6f5; }
.danger-themes button.theme-toggle { color: #9a555d; background: transparent; border-color: #e2bcc0; }
.danger-themes button.theme-toggle:hover { background: #fff6f5; border-color: #cb9298; }
.profit-verdict { margin-top: 0.75rem; padding: 0.65rem; border-radius: 8px; font-size: 0.72rem; font-weight: 800; }
.profit-verdict.pass { color: #1f6a4a; background: #e7f6ef; }
.profit-verdict.fail { color: #8a3e45; background: #fdeced; }
.breakdown { margin: 0.7rem 0 0; }
.breakdown div { display: flex; justify-content: space-between; padding: 0.4rem 0; border-bottom: 1px dashed #e2e6ed; font-size: 0.7rem; }
.breakdown dt { color: #788499; font-weight: 500; }
.breakdown dd { margin: 0; font-weight: 700; }
.evidence-link { margin-top: 0.8rem; padding: 0; font-size: 0.7rem; }
.decision-card { display: grid; grid-template-columns: 0.8fr 2fr auto; align-items: center; gap: 1.2rem; margin-top: 1rem; padding: 1.5rem; color: #173d2d; background: #e7f6ef; border: 1px solid #b9e1ce; border-radius: 16px; }
.decision-card.conditional,
.decision-card.limited { color: #594718; background: #fff7df; border-color: #ebd896; }
.decision-card.stop { color: #65343a; background: #fcedee; border-color: #e8bfc3; }
.decision-card span { font-size: 0.65rem; font-weight: 800; letter-spacing: 0.08em; }
.decision-card h3 { margin: 0.25rem 0 0; font-size: 1.2rem; }
.decision-card p { margin: 0; line-height: 1.55; }
.decision-card button { padding: 0.55rem 0.7rem; color: currentcolor; border: 1px solid currentcolor; border-radius: 7px; font-size: 0.68rem; }
.statement-columns { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }
.statement-group h4 { margin: 0 0 0.5rem; font-size: 0.8rem; }
.statement-group h4 span { color: #909bad; }
.statement-group article { margin-top: 0.5rem; padding: 0.75rem; background: #f6f8fb; border-left: 3px solid #7388c6; border-radius: 0 8px 8px 0; }
.statement-group article.statement-opportunity { border-color: #45a978; }
.statement-group article.statement-risk { border-color: #d16b74; }
.statement-group article.statement-action { border-color: #d29a3f; }
.statement-group article p { margin: 0; font-size: 0.75rem; line-height: 1.5; }
.statement-group article footer { display: flex; justify-content: space-between; margin-top: 0.5rem; color: #8a95a7; font-size: 0.63rem; }
.statement-group article button { padding: 0; font-size: 0.65rem; }
.empty-group,
.unavailable { margin: 0; padding: 1.4rem; color: #8792a5; background: #f7f8fa; border-radius: 9px; text-align: center; font-size: 0.75rem; }
.report-footer { display: flex; align-items: center; justify-content: space-between; margin: 1rem 0 2rem; padding: 1rem 1.3rem; color: #68758b; background: #fff; border: 1px solid #e0e5ed; border-radius: 13px; font-size: 0.75rem; }
@media (max-width: 991px) {
  .scope-strip { grid-template-columns: repeat(2, 1fr); }
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .two-column { grid-template-columns: 1fr; }
}
@media (max-width: 575px) {
  .report-hero,
  .decision-card { align-items: flex-start; grid-template-columns: 1fr; flex-direction: column; }
  .report-meta { align-items: flex-start; }
  .scope-strip,
  .metric-grid,
  .limitation-grid,
  .unavailable-metric-list,
  .statement-columns { grid-template-columns: 1fr; }
  .report-footer { align-items: flex-start; gap: 0.7rem; flex-direction: column; }
}
</style>
