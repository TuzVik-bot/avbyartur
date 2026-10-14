import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: { index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } },
};

export default function ModerationLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
