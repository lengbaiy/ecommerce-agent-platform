import { computed, ref } from "vue";

import { fetchOverview, fetchTasks, type AgentTask, type DashboardOverview } from "../api/operations";

export function useOperationsWorkspace() {
  const overview = ref<DashboardOverview>();
  const tasks = ref<AgentTask[]>([]);
  const loading = ref(true);
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

  return {
    overview,
    tasks,
    pendingTasks,
    loading,
    errorMessage,
    dataCutoff,
    loadWorkspace,
  };
}
