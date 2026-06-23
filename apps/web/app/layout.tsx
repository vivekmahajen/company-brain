import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Company Brain — Review Console",
  description: "Inspect, review, and route compiled company skills.",
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/sources", label: "Sources" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/skills", label: "Skills" },
  { href: "/policies", label: "Policies" },
  { href: "/evals", label: "Evals" },
  { href: "/review", label: "Review queue" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <aside className="w-56 shrink-0 border-r border-neutral-800 p-4">
            <div className="mb-6 text-lg font-semibold">🧠 Company Brain</div>
            <nav className="flex flex-col gap-1">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="rounded px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-800"
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          </aside>
          <main className="flex-1 p-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
