"use client";

import { useRouter } from "next/navigation";

export function FeedTopToggle({ checked, queryString }: { checked: boolean; queryString: string }) {
  const router = useRouter();
  return <form className="toggle-row" onSubmit={(event) => {
    event.preventDefault();
    const params = new URLSearchParams(queryString);
    const enabled = new FormData(event.currentTarget).has("top");
    if (enabled) params.set("top", "1"); else params.delete("top");
    params.delete("page");
    router.push(`/?${params.toString()}`);
  }}><label className="toggle-row"><input type="checkbox" name="top" value="1" defaultChecked={checked}/><span>Top companies only</span></label><button className="history-button" type="submit">Apply</button></form>;
}
