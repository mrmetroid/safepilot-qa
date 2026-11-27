import { useState } from "react";
import { validatePublicUrl } from "../lib/api";

interface Props {
  busy: boolean;
  onPreset: () => void;
  onCustom: (url: string) => void;
}

export function UrlBar({ busy, onPreset, onCustom }: Props) {
  const [url, setUrl] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const problem = validatePublicUrl(url);
    setErr(problem);
    if (!problem) onCustom(url.trim());
  };

  return (
    <div className="urlbar">
      <form onSubmit={submit} className="urlbar-form">
        <input
          type="url"
          inputMode="url"
          placeholder="Paste a preview URL, for example https://my-app.example.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={busy}
          aria-label="Preview URL"
        />
        <button type="submit" className="btn btn-primary" disabled={busy || !url.trim()}>
          Run QA Sweep
        </button>
      </form>
      <span className="urlbar-or">or</span>
      <button type="button" className="btn btn-preset" disabled={busy} onClick={onPreset}>
        Load Adversarial Test App (Demo Preset)
      </button>
      {err && <p className="urlbar-err">{err}</p>}
      <p className="urlbar-hint">
        Public http and https URLs only. Login walls and bot blockers can make a box fail honestly. Nothing is submitted without your approval.
      </p>
    </div>
  );
}
