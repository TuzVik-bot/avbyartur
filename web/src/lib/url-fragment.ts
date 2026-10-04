"use client";

import { useEffect, useState } from "react";

/** Read an opaque action token from the URL fragment, then scrub it from browser history. */
export function useUrlFragmentToken() {
  const [token, setToken] = useState("");

  useEffect(() => {
    const rawHash = window.location.hash;
    if (!rawHash) return;
    const fragment = new URLSearchParams(rawHash.slice(1));
    const value = fragment.get("token")?.trim().slice(0, 2048);
    if (!value) return;
    setToken(value);
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}`);
  }, []);

  return token;
}
