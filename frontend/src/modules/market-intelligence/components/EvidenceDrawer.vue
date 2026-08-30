<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";

import type {
  CompetitorItem,
  EvidenceReference,
  JsonValue,
} from "../types/marketIntelligence";

defineProps<{
  evidence: EvidenceReference[];
  product?: CompetitorItem | null;
}>();
const emit = defineEmits<{ close: [] }>();

function dateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function safeQueryRange(value: Record<string, JsonValue>) {
  const blocked = /path|cookie|token|authorization|secret/i;
  return Object.fromEntries(Object.entries(value).filter(([key]) => !blocked.test(key)));
}

function safeSource(value: string) {
  return value.split(/[\\/]/).at(-1) || "固定数据集";
}

function productSales(product: CompetitorItem) {
  return product.sales_display ?? product.sales_value?.toLocaleString("zh-CN") ?? "暂无数据";
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") emit("close");
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <Teleport to="body">
    <div class="drawer-layer" role="presentation" @click.self="emit('close')">
      <aside class="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-title">
        <header>
          <div>
            <span>Evidence trail</span>
            <h2 id="evidence-title">证据来源</h2>
            <p>{{ evidence.length }} 条可追溯记录</p>
          </div>
          <button type="button" aria-label="关闭证据抽屉" @click="emit('close')">×</button>
        </header>

        <div class="drawer-content">
          <section v-if="product" class="product-snapshot" aria-labelledby="product-snapshot-title">
            <div class="snapshot-heading">
              <div>
                <span>本次报告使用的商品数据</span>
                <h3 id="product-snapshot-title">{{ product.title }}</h3>
              </div>
              <b>#{{ product.rank }}</b>
            </div>
            <dl>
              <div><dt>商品 ID</dt><dd>{{ product.product_id }}</dd></div>
              <div><dt>品牌</dt><dd>{{ product.brand || "—" }}</dd></div>
              <div><dt>平台 / 市场</dt><dd>{{ product.platform }} / {{ product.market }}</dd></div>
              <div><dt>店铺</dt><dd>{{ product.shop_name || "—" }}</dd></div>
              <div><dt>价格</dt><dd>{{ product.currency }} {{ product.price }}</dd></div>
              <div><dt>可见销量</dt><dd>{{ productSales(product) }}</dd></div>
              <div><dt>评分</dt><dd>{{ product.rating ?? "—" }}</dd></div>
              <div><dt>评论数</dt><dd>{{ product.review_count?.toLocaleString("zh-CN") ?? "—" }}</dd></div>
            </dl>
          </section>

          <div v-if="product" class="trace-divider">
            <span>数据来源与追溯信息</span>
          </div>

          <article v-for="item in evidence" :key="item.evidence_id" class="evidence-item">
            <div class="evidence-topline">
              <span class="grade" :class="`grade-${item.data_level.toLowerCase()}`">
                {{ item.data_level }} 级
              </span>
              <span>{{ item.evidence_type }}</span>
              <code>#{{ item.evidence_id.slice(0, 10) }}</code>
            </div>
            <h3>{{ safeSource(item.data_source) }}</h3>

            <dl>
              <div><dt>平台</dt><dd>{{ item.platform }}</dd></div>
              <div><dt>商品 ID</dt><dd>{{ item.product_id || "—" }}</dd></div>
              <div><dt>评论 ID</dt><dd>{{ item.review_id || "—" }}</dd></div>
              <div><dt>来源时间</dt><dd>{{ dateTime(item.source_timestamp) }}</dd></div>
              <div><dt>入库时间</dt><dd>{{ dateTime(item.ingest_timestamp) }}</dd></div>
              <div><dt>数据版本</dt><dd>{{ item.data_version }}</dd></div>
              <div><dt>商品样本</dt><dd>{{ item.sample_scope.actual_product_count }}</dd></div>
              <div><dt>评论样本</dt><dd>{{ item.sample_scope.actual_review_count }}</dd></div>
            </dl>

            <div class="query-scope">
              <strong>查询范围</strong>
              <pre>{{ JSON.stringify(safeQueryRange(item.query_range), null, 2) }}</pre>
            </div>
            <footer>
              <span>快照已固化</span>
              <code>SHA-256 {{ item.sha256.slice(0, 16) }}…</code>
            </footer>
          </article>
        </div>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.drawer-layer { position: fixed; z-index: 1100; inset: 0; display: flex; justify-content: flex-end; background: rgb(15 23 42 / 48%); backdrop-filter: blur(2px); }
.evidence-drawer { width: min(520px, 94vw); height: 100%; overflow: hidden; color: #1b263b; background: #f7f9fc; box-shadow: -20px 0 60px rgb(15 23 42 / 22%); animation: enter 0.2s ease-out; }
header { display: flex; align-items: flex-start; justify-content: space-between; padding: 1.5rem; color: #eff4ff; background: #17223a; }
header span { color: #91a4cc; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.13em; text-transform: uppercase; }
header h2 { margin: 0.25rem 0 0; font-size: 1.45rem; }
header p { margin: 0.2rem 0 0; color: #a8b5d0; font-size: 0.78rem; }
header button { width: 36px; height: 36px; color: #dbe4f7; background: rgb(255 255 255 / 8%); border: 0; border-radius: 50%; font-size: 1.5rem; line-height: 1; }
.drawer-content { height: calc(100% - 112px); padding: 1rem; overflow: auto; }
.product-snapshot { margin-bottom: 1rem; padding: 1.15rem; background: linear-gradient(145deg, #fff, #f2f6ff); border: 1px solid #cfdaf0; border-radius: 14px; box-shadow: 0 8px 22px rgb(48 75 128 / 8%); }
.snapshot-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
.snapshot-heading span { color: #64769b; font-size: 0.67rem; font-weight: 800; letter-spacing: 0.08em; }
.snapshot-heading h3 { margin: 0.3rem 0 0; color: #1d2b48; line-height: 1.4; }
.snapshot-heading b { flex: 0 0 auto; padding: 0.25rem 0.5rem; color: #315598; background: #e4ecfc; border-radius: 6px; font-size: 0.72rem; }
.product-snapshot dd { color: #263856; font-weight: 700; }
.trace-divider { display: flex; align-items: center; gap: 0.65rem; margin: 0.2rem 0 0.8rem; color: #75829a; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.08em; }
.trace-divider::after { height: 1px; background: #dfe5ef; content: ""; flex: 1; }
.evidence-item { margin-bottom: 0.9rem; padding: 1.1rem; background: white; border: 1px solid #dfe5ef; border-radius: 14px; box-shadow: 0 8px 20px rgb(30 49 82 / 5%); }
.evidence-topline { display: flex; align-items: center; gap: 0.5rem; color: #6d7890; font-size: 0.68rem; text-transform: uppercase; }
.evidence-topline code { margin-left: auto; color: #8792a7; }
.grade { padding: 0.2rem 0.45rem; border-radius: 5px; font-weight: 800; }
.grade-a { color: #146342; background: #dcf4e9; }
.grade-b { color: #2954a5; background: #e4edff; }
.grade-c,
.grade-d { color: #7b5b16; background: #fff1ca; }
h3 { margin: 0.8rem 0; font-size: 1rem; }
dl { display: grid; grid-template-columns: 1fr 1fr; gap: 0.65rem 1rem; margin: 0; }
dl div { min-width: 0; }
dt { color: #8792a7; font-size: 0.67rem; font-weight: 600; }
dd { margin: 0.12rem 0 0; overflow: hidden; color: #36435a; font-size: 0.76rem; text-overflow: ellipsis; white-space: nowrap; }
.query-scope { margin-top: 0.9rem; padding: 0.75rem; background: #f3f6fa; border-radius: 9px; }
.query-scope strong { font-size: 0.7rem; }
pre { max-height: 130px; margin: 0.4rem 0 0; overflow: auto; color: #536078; font-size: 0.66rem; white-space: pre-wrap; }
.evidence-item footer { display: flex; justify-content: space-between; gap: 0.5rem; margin-top: 0.8rem; color: #7b879d; font-size: 0.65rem; }
@keyframes enter { from { transform: translateX(100%); } to { transform: translateX(0); } }
@media (prefers-reduced-motion: reduce) { .evidence-drawer { animation: none; } }
</style>
