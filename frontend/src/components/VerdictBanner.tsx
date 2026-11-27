import { useState } from "react";
import { copyText } from "../lib/api";
import type { Verdict } from "../lib/types";

interface Props {
  verdict: Verdict;
  headline: string | null;
  fixPrompt: string | null;
}

export function VerdictBanner({ verdict, headline, fixPrompt }: Props) {
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null);
  const ship = verdict === "SHIP IT";
  const copy = async () => {
    if (!fixPrompt) return;
    setCopied((await copyText(fixPrompt)) ? "ok" : "fail");
    window.setTimeout(() => setCopied(null), 2500);
  };
  return (
    <section className={`verdict ${ship ? "verdict-ship" : "verdict-stop"}`} aria-live="assertive">
      <div>
        <div className="verdict-word">{verdict}</div>
        {headline && <p className="verdict-headline">{headline}</p>}
      </div>
      {fixPrompt && (
        <button className="btn btn-copy" onClick={copy}>
          {copied === "ok" ? "Copied" : copied === "fail" ? "Copy failed, select below" : "Copy Fix Prompt for Cursor"}
        </button>
      )}
    </section>
  );
}
