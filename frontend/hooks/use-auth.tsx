"use client";

// Session context. The backend is the source of truth for roles; this only
// mirrors what GET /auth/me returns.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { apiFetch, API_V1 } from "@/lib/api";
import type { MeOut, Role } from "@/lib/types";

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  org_name: string;
}

interface AuthContextValue {
  me: MeOut | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  role: Role | undefined;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const data = await apiFetch<MeOut>(`${API_V1}/auth/me`);
      if (mounted.current) setMe(data);
    } catch {
      if (mounted.current) setMe(null);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const onUnauthorized = () => {
      setMe(null);
      router.replace("/login");
    };
    window.addEventListener("sentinel:unauthorized", onUnauthorized);
    return () => {
      mounted.current = false;
      window.removeEventListener("sentinel:unauthorized", onUnauthorized);
    };
  }, [refresh, router]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await apiFetch<MeOut>(`${API_V1}/auth/login`, {
      method: "POST",
      body: { email, password },
    });
    setMe(data);
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    const data = await apiFetch<MeOut>(`${API_V1}/auth/register`, {
      method: "POST",
      body: input,
    });
    setMe(data);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch<void>(`${API_V1}/auth/logout`, { method: "POST" });
    } finally {
      setMe(null);
      router.replace("/login");
    }
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({ me, loading, login, register, logout, refresh, role: me?.role }),
    [me, loading, login, register, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
