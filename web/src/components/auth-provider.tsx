"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, resetCsrfToken, setCsrfToken } from "@/lib/api";
import type { AuthSession, User } from "@/lib/types";

type AuthContextValue = {
  user: User | null;
  setSession: (session: AuthSession | null) => void;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children, initialSession }: { children: React.ReactNode; initialSession: AuthSession | null }) {
  const [user, setUser] = useState<User | null>(initialSession?.user ?? null);
  const router = useRouter();

  useEffect(() => {
    setCsrfToken(initialSession?.csrf_token);
  }, [initialSession?.csrf_token]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    setSession(session) {
      setUser(session?.user ?? null);
      setCsrfToken(session?.csrf_token);
      if (!session) resetCsrfToken();
    },
    async signOut() {
      await api.logout();
      setUser(null);
      resetCsrfToken();
      router.push("/");
      router.refresh();
    }
  }), [user, router]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
