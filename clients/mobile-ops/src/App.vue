<script setup lang="ts">
import { computed, ref } from "vue";

const activeView = ref<"overview" | "tasks">("overview");
const metrics = [
  { label: "今日 GMV", value: "¥128,640", change: "+8.4%" },
  { label: "转化率", value: "3.86%", change: "-0.3%" },
  { label: "库存风险", value: "12", change: "3 个高风险" },
];
const title = computed(() => (activeView.value === "overview" ? "今日经营" : "Agent 任务"));
</script>

<template>
  <main class="app-shell">
    <header>
      <span class="eyebrow">COMMERCE AGENT</span>
      <h1>{{ title }}</h1>
      <p>Amazon US 演示店 · 移动运营端开发基线</p>
    </header>

    <section v-if="activeView === 'overview'" class="metric-grid">
      <article v-for="metric in metrics" :key="metric.label" class="card">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <small>{{ metric.change }}</small>
      </article>
    </section>
    <section v-else class="card task-card">
      <h2>待处理任务</h2>
      <p>任务、审批与告警接口将在此接入共享 API Client。</p>
    </section>

    <nav aria-label="移动端主导航">
      <button :class="{ active: activeView === 'overview' }" @click="activeView = 'overview'">
        经营总览
      </button>
      <button :class="{ active: activeView === 'tasks' }" @click="activeView = 'tasks'">
        Agent 任务
      </button>
    </nav>
  </main>
</template>

<style>
:root {
  font-family: Inter, "Microsoft YaHei", sans-serif;
  color: #182230;
  background: #f4f6f9;
}
* { box-sizing: border-box; }
body { margin: 0; }
button { font: inherit; }
.app-shell { min-height: 100vh; max-width: 720px; margin: auto; padding: 28px 20px 96px; }
header { margin-bottom: 24px; }
.eyebrow { color: #5856d6; font-size: 12px; font-weight: 800; letter-spacing: 0.16em; }
h1 { margin: 8px 0; font-size: 30px; }
header p, .task-card p { margin: 0; color: #667085; }
.metric-grid { display: grid; gap: 14px; grid-template-columns: repeat(3, 1fr); }
.card { padding: 20px; border: 1px solid #e4e7ec; border-radius: 16px; background: white; box-shadow: 0 6px 20px rgb(16 24 40 / 5%); }
.card span, .card small { display: block; color: #667085; }
.card strong { display: block; margin: 12px 0 6px; font-size: 24px; }
.task-card { min-height: 180px; }
nav { position: fixed; right: 0; bottom: 0; left: 0; display: flex; justify-content: center; gap: 8px; padding: 12px 20px max(12px, env(safe-area-inset-bottom)); border-top: 1px solid #e4e7ec; background: rgb(255 255 255 / 94%); backdrop-filter: blur(12px); }
nav button { min-width: 130px; padding: 11px 18px; border: 0; border-radius: 10px; color: #667085; background: transparent; }
nav button.active { color: white; background: #5856d6; }
@media (max-width: 560px) { .metric-grid { grid-template-columns: 1fr; } }
</style>
