"use client";

import { create } from "zustand";


type AuthUser = {
  id: string;
  nickname: string;
};

type AppState = {
  token: string | null;
  user: AuthUser | null;
  setSession: (token: string, user: AuthUser) => void;
  clearSession: () => void;
  hydrate: () => void;
};

const TOKEN_KEY = "fushengliunian.token";
const USER_KEY = "fushengliunian.user";

export const useAppStore = create<AppState>((set) => ({
  token: null,
  user: null,
  setSession: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    set({ token, user });
  },
  clearSession: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    set({ token: null, user: null });
  },
  hydrate: () => {
    if (typeof window === "undefined") {
      return;
    }
    const token = localStorage.getItem(TOKEN_KEY);
    const user = localStorage.getItem(USER_KEY);
    set({
      token,
      user: user ? (JSON.parse(user) as AuthUser) : null,
    });
  },
}));
