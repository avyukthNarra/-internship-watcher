"use client";

import { useEffect, useState } from "react";

export function NewTodayBadge({ firstSeen }: { firstSeen: string }) {
  const [isToday, setIsToday] = useState(false);
  useEffect(() => {
    const firstSeenLocal = new Date(firstSeen).toLocaleDateString();
    setIsToday(firstSeenLocal === new Date().toLocaleDateString());
  }, [firstSeen]);
  return isToday ? <span className="chip fresh">New today</span> : null;
}
