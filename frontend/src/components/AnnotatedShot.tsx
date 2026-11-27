import type { Shot, VisionBug } from "../lib/types";

/** Draws red rectangles from Box 2 bbox values ([x, y, w, h] in screenshot CSS px). */
export function AnnotatedShot({ shot, bugs }: { shot: Shot; bugs: VisionBug[] }) {
  const W = shot.width || 390;
  const H = shot.height || 844;
  return (
    <div className="annotated" style={{ aspectRatio: `${W} / ${H}` }}>
      <img src={shot.src} alt="Annotated screenshot" />
      {bugs.map((b, i) => {
        if (!hasBox(b)) return null;
        const [x, y, w, h] = b.bbox;
        return (
          <div
            key={b.id}
            className={`bbox sev-${b.severity}`}
            style={{ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%`, width: `${(w / W) * 100}%`, height: `${(h / H) * 100}%` }}
          >
            <span className="bbox-label">{i + 1}</span>
          </div>
        );
      })}
    </div>
  );
}

/** LLM output: only draw well-formed [x, y, w, h] boxes. */
export function hasBox(b: VisionBug): boolean {
  return Array.isArray(b?.bbox) && b.bbox.length === 4 && b.bbox.every((n) => Number.isFinite(n));
}
