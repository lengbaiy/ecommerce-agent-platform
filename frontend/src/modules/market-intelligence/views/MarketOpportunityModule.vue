<script setup lang="ts">
import { ref } from "vue";

import { useMarketIntelligenceStore } from "../store/marketIntelligence";
import MarketOpportunityOverview from "./MarketOpportunityOverview.vue";
import MarketOpportunityView from "./MarketOpportunityView.vue";
import MarketMetricManagement from "./MarketMetricManagement.vue";

type MarketPage = "overview" | "create" | "metrics";

const query = new URLSearchParams(window.location.search);
const store = useMarketIntelligenceStore();
const requestedPage = query.get("market_view");
const page = ref<MarketPage>(
  query.has("task_id") || requestedPage === "create"
    ? "create"
    : requestedPage === "metrics"
      ? "metrics"
      : "overview",
);

function updateUrl(nextPage: MarketPage, taskId?: string) {
  const url = new URL(window.location.href);
  if (nextPage !== "overview") url.searchParams.set("market_view", nextPage);
  else url.searchParams.delete("market_view");
  if (taskId) url.searchParams.set("task_id", taskId);
  else url.searchParams.delete("task_id");
  window.history.replaceState({}, "", url);
}

function createAnalysis() {
  store.startNewAnalysis();
  updateUrl("create");
  page.value = "create";
}

function openTask(taskId: string) {
  store.startNewAnalysis();
  updateUrl("create", taskId);
  page.value = "create";
}

function showOverview() {
  updateUrl("overview");
  page.value = "overview";
}

function showMetrics() {
  updateUrl("metrics");
  page.value = "metrics";
}
</script>

<template>
  <MarketOpportunityOverview
    v-if="page === 'overview'"
    @create="createAnalysis"
    @task="openTask"
    @metrics="showMetrics"
  />
  <MarketMetricManagement v-else-if="page === 'metrics'" @back="showOverview" />
  <div v-else class="analysis-page">
    <button type="button" class="back-button" @click="showOverview">← 返回市场概览</button>
    <MarketOpportunityView @metrics="showMetrics" />
  </div>
</template>

<style scoped>
.analysis-page { max-width: 1320px; margin: 0 auto; }
.back-button { margin: 0.4rem 0 0.35rem; padding: 0.4rem 0; color: #526a9f; background: transparent; border: 0; font-size: 0.72rem; font-weight: 750; }
.back-button:hover { color: #294891; }
.back-button:focus-visible { outline: 2px solid #4664bc; outline-offset: 3px; border-radius: 3px; }
</style>
