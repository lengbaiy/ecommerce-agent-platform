import { computed, ref } from "vue";

import {
  createMarketTask,
  fetchOverview,
  fetchTasks,
  type AgentTask,
  type DashboardOverview,
} from "../api/operations";

export function useOperationsWorkspace() {
  const overview = ref<DashboardOverview>();
  const tasks = ref<AgentTask[]>([]);
  const loading = ref(true);
  const creating = ref(false);
  const errorMessage = ref("");
  const pendingTasks = computed(() =>
    tasks.value.filter((task) => task.status === "WAITING_APPROVAL"),
  );
  const dataCutoff = computed(() => {
    if (!overview.value) return "--";
    return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
      new Date(overview.value.data_cutoff),
    );
  });

  async function loadWorkspace(shopId = "amazon-us-demo") {
    loading.value = true;
    errorMessage.value = "";
    try {
      const [overviewData, taskData] = await Promise.all([fetchOverview(shopId), fetchTasks()]);
      overview.value = overviewData;
      tasks.value = taskData.items;
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "无法加载经营数据";
    } finally {
      loading.value = false;
    }
  }

  async function createTask(shopId = "amazon-us-demo") {
    creating.value = true;
    try {
      await createMarketTask(shopId);
      await loadWorkspace(shopId);
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "创建任务失败";
    } finally {
      creating.value = false;
    }
  }

  return {
    overview,
    tasks,
    pendingTasks,
    loading,
    creating,
    errorMessage,
    dataCutoff,
    loadWorkspace,
    createTask,
  };
}
