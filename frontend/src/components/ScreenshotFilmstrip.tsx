import type { Shot } from "../lib/types";

export function ScreenshotFilmstrip({ shots, onOpen }: { shots: Shot[]; onOpen: (s: Shot) => void }) {
  if (shots.length === 0) return <div className="filmstrip filmstrip-empty">No screenshots yet</div>;
  return (
    <div className="filmstrip">
      {[...shots].reverse().map((s) => (
        <button key={s.step} className="thumb" onClick={() => onOpen(s)} title={`Step ${s.step}`}>
          <img src={s.src} alt={`Step ${s.step} screenshot`} loading="lazy" />
          <span>#{s.step}</span>
        </button>
      ))}
    </div>
  );
}
