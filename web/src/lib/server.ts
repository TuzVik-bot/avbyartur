import { redirect } from "next/navigation";
import { getSessionServer } from "@/lib/server-api";

export async function requireSession(nextPath: string) {
  const session = await getSessionServer();
  if (!session) redirect(`/login?next=${encodeURIComponent(nextPath)}`);
  return session;
}
