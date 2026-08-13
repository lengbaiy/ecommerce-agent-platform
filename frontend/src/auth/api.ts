import { authenticatedFetch, type LoginSession, type SessionUser } from "./session";

export type CaptchaChallenge = {
  provider: "local_puzzle";
  captcha_id: string;
  track_length: number;
  canvas_width: number;
  canvas_height: number;
  puzzle_offset: number;
  expires_in: number;
};

export async function createCaptcha() {
  const response = await fetch("/api/v1/auth/captcha", { method: "POST" });
  if (!response.ok) throw new Error("验证码加载失败");
  return response.json() as Promise<CaptchaChallenge>;
}

export async function login(payload: {
  tenant_id: string;
  username: string;
  password: string;
  captcha_id: string;
  slider_position: number;
}) {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string | Array<{ msg?: string }>;
    } | null;
    const detail = Array.isArray(body?.detail)
      ? body.detail
          .map((item) => item.msg)
          .filter(Boolean)
          .join("；")
      : body?.detail;
    if (response.status === 422) throw new Error(detail || "登录信息格式不正确");
    if (response.status === 401) {
      if (detail === "slider verification failed") {
        throw new Error("拼图位置未通过服务端校验，请刷新后重新拖动");
      }
      if (detail === "slider challenge is missing, expired or already used") {
        throw new Error("拼图验证已过期或已使用，请刷新后重新验证");
      }
      if (detail === "account is temporarily locked") {
        throw new Error("账号因连续失败已临时锁定，请稍后再试");
      }
      throw new Error("租户、账号或密码不正确");
    }
    throw new Error(typeof detail === "string" ? detail : "登录服务暂时不可用");
  }
  return response.json() as Promise<LoginSession>;
}

export async function logout() {
  await authenticatedFetch("/api/v1/auth/logout", { method: "POST" });
}

export async function fetchUsers() {
  const response = await authenticatedFetch("/api/v1/auth/users");
  if (!response.ok) throw new Error("用户列表加载失败");
  return response.json() as Promise<{ items: SessionUser[]; total: number }>;
}

export async function createUser(payload: {
  username: string;
  display_name: string;
  password: string;
  roles: string[];
}) {
  const response = await authenticatedFetch("/api/v1/auth/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("用户创建失败");
  return response.json() as Promise<SessionUser>;
}

export async function updateUser(
  userId: string,
  payload: { display_name?: string; password?: string; roles?: string[]; enabled?: boolean },
) {
  const response = await authenticatedFetch(`/api/v1/auth/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? "用户更新失败");
  }
  return response.json() as Promise<SessionUser>;
}
