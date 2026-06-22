"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "../../lib/api";

export default function ReviewButtons({ slug }: { slug: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function decide(decision: "approve" | "deprecate") {
    setBusy(true);
    try {
      await api.reviewSkill(slug, decision);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex gap-2">
      <button
        onClick={() => decide("approve")}
        disabled={busy}
        className="rounded bg-emerald-600 px-3 py-1.5 text-sm hover:bg-emerald-500 disabled:opacity-50"
      >
        Approve
      </button>
      <button
        onClick={() => decide("deprecate")}
        disabled={busy}
        className="rounded bg-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-600 disabled:opacity-50"
      >
        Deprecate
      </button>
    </div>
  );
}
