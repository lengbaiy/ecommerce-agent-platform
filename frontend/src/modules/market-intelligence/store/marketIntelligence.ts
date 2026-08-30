import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
  MarketIntelligenceApiError,
  cancelMarketTask,
  createMarketIntelligenceTask,
  getMarketTask,
  previewMarketTask,
  streamMarketTaskEvents,
} from "../api/marketIntelligence";
import type {
  AgentTask,
  CompetitorItem,
  EvidenceReference,
  MarketIntelligenceReport,
  MarketIntelligenceRequest,
  TaskEvent,
  TaskPreviewResponse,
} from "../types/marketIntelligence";

const storageKey = "market-intelligence:last-task-id";
const terminalStatuses = new Set(["COMPLETED", "DEGRADED", "FAILED", "CANCELLED"]);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "市场分析请求失败，请稍后重试";
}

function cloneRequest(value: MarketIntelligenceRequest): MarketIntelligenceRequest {
  return JSON.parse(JSON.stringify(value)) as MarketIntelligenceRequest;
}

function taskIdFromLocation(): string | null {
  return new URLSearchParams(window.location.search).get("task_id");
}

function rememberTask(taskId: string | null) {
  const url = new URL(window.location.href);
  if (taskId) {
    localStorage.setItem(storageKey, taskId);
    url.searchParams.set("task_id", taskId);
  } else {
    localStorage.removeItem(storageKey);
    url.searchParams.delete("task_id");
  }
  window.history.replaceState({}, "", url);
}

export const useMarketIntelligenceStore = defineStore("market-intelligence", () => {
  const userQuery = ref("");
  const preview = ref<TaskPreviewResponse | null>(null);
  const draft = ref<MarketIntelligenceRequest | null>(null);
  const task = ref<AgentTask | null>(null);
  const events = ref<TaskEvent[]>([]);
  const previewing = ref(false);
  const submitting = ref(false);
  const restoring = ref(false);
  const cancelling = ref(false);
  const streaming = ref(false);
  const error = ref("");
  const fieldError = ref("");
  const selectedEvidenceIds = ref<string[]>([]);
  const selectedEvidenceProduct = ref<CompetitorItem | null>(null);
  let eventController: AbortController | null = null;

  const isTerminal = computed(() => Boolean(task.value && terminalStatuses.has(task.value.status)));
  const report = computed<MarketIntelligenceReport | null>(() => {
    const payload = task.value?.result?.payload;
    if (!payload || !("market_intelligence_report" in payload)) return null;
    return payload.market_intelligence_report as MarketIntelligenceReport;
  });
  const selectedEvidence = computed<EvidenceReference[]>(() => {
    const references = report.value?.evidence_refs ?? [];
    const wanted = new Set(selectedEvidenceIds.value);
    return references.filter((item) => wanted.has(item.evidence_id));
  });

  function mergeEvent(incoming: TaskEvent) {
    if (events.value.some((item) => item.event_id === incoming.event_id)) return;
    events.value.push(incoming);
    events.value.sort((left, right) => left.timestamp.localeCompare(right.timestamp));
    if (task.value) {
      task.value = {
        ...task.value,
        status: incoming.status,
        current_step: incoming.step ?? task.value.current_step,
        state_version: Math.max(task.value.state_version, incoming.state_version),
      };
    }
  }

  function updateQuery(value: string) {
    if (value === userQuery.value) return;
    userQuery.value = value;
    preview.value = null;
    draft.value = null;
    error.value = "";
    fieldError.value = "";
  }

  function captureError(caught: unknown) {
    error.value = errorMessage(caught);
    fieldError.value = "";
    if (!(caught instanceof MarketIntelligenceApiError)) return;
    const detail = caught.detail;
    if (!detail || typeof detail !== "object" || !("details" in detail)) return;
    const details = (detail as { details?: unknown }).details;
    if (details && typeof details === "object" && "field" in details) {
      fieldError.value = String((details as { field: unknown }).field);
    }
  }

  async function runPreview() {
    if (userQuery.value.trim().length < 5) {
      error.value = "请至少用 5 个字描述希望分析的商品和市场";
      return;
    }
    previewing.value = true;
    error.value = "";
    try {
      const result = await previewMarketTask(userQuery.value.trim());
      preview.value = result;
      draft.value = result.normalized_input ? cloneRequest(result.normalized_input) : null;
    } catch (caught) {
      captureError(caught);
    } finally {
      previewing.value = false;
    }
  }

  async function submitTask(input: MarketIntelligenceRequest) {
    if (submitting.value) return;
    submitting.value = true;
    error.value = "";
    try {
      const created = await createMarketIntelligenceTask(userQuery.value.trim(), input);
      task.value = created;
      events.value = [...created.events];
      rememberTask(created.id);
      void followTask(created.id);
    } catch (caught) {
      captureError(caught);
    } finally {
      submitting.value = false;
    }
  }

  async function refreshTask(taskId: string) {
    const current = await getMarketTask(taskId);
    task.value = current;
    current.events.forEach(mergeEvent);
  }

  async function followTask(taskId: string) {
    eventController?.abort();
    const controller = new AbortController();
    eventController = controller;
    streaming.value = true;
    try {
      while (!controller.signal.aborted) {
        try {
          await streamMarketTaskEvents(taskId, {
            signal: controller.signal,
            lastEventId: events.value.at(-1)?.event_id,
            onEvent: mergeEvent,
          });
          await refreshTask(taskId);
          if (isTerminal.value) break;
        } catch (caught) {
          if (caught instanceof DOMException && caught.name === "AbortError") break;
          error.value = `进度连接中断，正在自动恢复：${errorMessage(caught)}`;
          try {
            await refreshTask(taskId);
            if (isTerminal.value) break;
          } catch {
            // 下一轮仍会从最后一个事件继续恢复。
          }
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
    } finally {
      if (eventController === controller) {
        eventController = null;
        streaming.value = false;
      }
    }
  }

  async function restoreTask() {
    const taskId = taskIdFromLocation() || localStorage.getItem(storageKey);
    if (!taskId || restoring.value) return;
    restoring.value = true;
    error.value = "";
    fieldError.value = "";
    try {
      await refreshTask(taskId);
      rememberTask(taskId);
      if (!isTerminal.value) void followTask(taskId);
    } catch (caught) {
      rememberTask(null);
      error.value = `无法恢复上次任务：${errorMessage(caught)}`;
    } finally {
      restoring.value = false;
    }
  }

  async function cancelCurrentTask() {
    if (!task.value || isTerminal.value || cancelling.value) return;
    cancelling.value = true;
    error.value = "";
    fieldError.value = "";
    try {
      const cancelled = await cancelMarketTask(task.value.id);
      task.value = cancelled;
      cancelled.events.forEach(mergeEvent);
    } catch (caught) {
      error.value = errorMessage(caught);
    } finally {
      cancelling.value = false;
    }
  }

  function startNewAnalysis() {
    eventController?.abort();
    preview.value = null;
    draft.value = null;
    task.value = null;
    events.value = [];
    selectedEvidenceIds.value = [];
    selectedEvidenceProduct.value = null;
    error.value = "";
    fieldError.value = "";
    rememberTask(null);
  }

  function showEvidence(ids: string[], product?: CompetitorItem) {
    selectedEvidenceIds.value = [...new Set(ids)];
    selectedEvidenceProduct.value = product ?? null;
  }

  function closeEvidence() {
    selectedEvidenceIds.value = [];
    selectedEvidenceProduct.value = null;
  }

  function stopFollowing() {
    eventController?.abort();
    eventController = null;
    streaming.value = false;
  }

  return {
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
    runPreview,
    submitTask,
    restoreTask,
    cancelCurrentTask,
    startNewAnalysis,
    showEvidence,
    closeEvidence,
    updateQuery,
    stopFollowing,
  };
});
