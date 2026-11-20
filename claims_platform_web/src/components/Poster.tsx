import type { CSSProperties, ReactNode } from "react";

// Poster art for a client, drawn with CSS gradients from the client code so every client gets the
// same artwork everywhere (card, billboard, client page) without any image files.
function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function posterStyle(seed: string): CSSProperties {
  const h = hash(seed);
  const hue = h % 360;
  const hue2 = (hue + 35 + ((h >> 9) % 70)) % 360;
  const x = 20 + ((h >> 4) % 60);
  const y = 15 + ((h >> 12) % 50);
  return {
    backgroundImage: [
      `radial-gradient(circle at ${x}% ${y}%, hsla(${hue}, 80%, 55%, 0.85) 0%, hsla(${hue}, 80%, 40%, 0) 55%)`,
      `radial-gradient(circle at ${100 - x}% ${100 - y / 2}%, hsla(${hue2}, 75%, 45%, 0.75) 0%, hsla(${hue2}, 75%, 30%, 0) 60%)`,
      `linear-gradient(135deg, hsl(${hue}, 45%, 14%) 0%, hsl(${hue2}, 50%, 9%) 100%)`,
    ].join(", "),
  };
}

// The initials shown large and faint across the art: "B-BIRCH" -> "B", "C2-CEDAR-WEST" -> "C2".
export function glyph(code: string): string {
  return (code.split("-")[0] || code).slice(0, 2).toUpperCase();
}

export function Poster({ seed, label, className = "", children }: { seed: string; label?: string; className?: string; children?: ReactNode }) {
  return (
    <div className={`poster ${className}`.trim()} style={posterStyle(seed)} aria-hidden={children ? undefined : true}>
      {label && <span className="glyph" aria-hidden="true">{label}</span>}
      {children}
    </div>
  );
}

// A stable avatar colour for the signed-in person.
export function avatarStyle(seed: string): CSSProperties {
  const hue = hash(seed) % 360;
  return { background: `linear-gradient(135deg, hsl(${hue}, 70%, 45%), hsl(${(hue + 40) % 360}, 70%, 30%))` };
}
