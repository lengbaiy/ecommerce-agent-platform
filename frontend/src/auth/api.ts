import { authenticatedFetch, type LoginSession, type SessionUser } from "./session";

export type CaptchaChallenge = {
  id: string;
  image_url: string;
  tolerance: number;
  expires_in: number;
};

export async function createCaptcha() {
  const response = await fetch("/api/v1/auth/captcha", { method: "POST" });
  if (!response.ok) throw new Error("验证码加载失败");
  return response.json() as Promise<CaptchaChallenge>;
}

export async function verifyCaptcha(id: string, position: number) {
  const response = await fetch(
    `/api/v1/auth/captcha/${encodeURIComponent(id)}/verify?position=${position}`,
    { method: "POST" },
  );
  if (!response.ok) throw new Error("滑块位置不正确，请重试");
}

export async function login(payload: {
  tenant_id: string;
  username: string;
  password: string;
  captcha_id: string;
}) {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("登录失败，请检查账号、密码与验证码");
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
