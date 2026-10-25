import { useEffect, useRef } from "react";

// Steam's Quick Access Menu doesn't scroll a Decky plugin's panel by touch: dragging on it does nothing. This drags the
// panel's scroll container along with the finger (and lets it glide on after a flick), and a drag isn't taken as a tap.
const DRAG_PX = 8; // movement before a touch counts as a drag, not a tap
const FRICTION = 0.95; // per frame, for the glide after a flick

function scroller(el: HTMLElement | null): HTMLElement | null {
  for (let e = el?.parentElement ?? null; e; e = e.parentElement) {
    const { overflowY } = getComputedStyle(e);
    if ((overflowY === "auto" || overflowY === "scroll") && e.scrollHeight > e.clientHeight) return e;
  }
  return null;
}

export function useTouchScroll<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    let target: HTMLElement | null = null;
    let startY = 0;
    let lastY = 0;
    let lastT = 0;
    let velocity = 0; // px per ms
    let dragging = false;
    let draggedAt = 0;
    let glide = 0;

    const stopGlide = () => {
      cancelAnimationFrame(glide);
      glide = 0;
    };
    const start = (e: TouchEvent) => {
      if (e.touches.length !== 1) return;
      stopGlide();
      target = scroller(root);
      startY = lastY = e.touches[0].clientY;
      lastT = performance.now();
      velocity = 0;
      dragging = false;
    };
    const move = (e: TouchEvent) => {
      if (!target || e.touches.length !== 1) return;
      const y = e.touches[0].clientY;
      if (!dragging && Math.abs(y - startY) < DRAG_PX) return;
      dragging = true;
      const now = performance.now();
      target.scrollTop -= y - lastY;
      velocity = (y - lastY) / Math.max(1, now - lastT);
      lastY = y;
      lastT = now;
    };
    const end = () => {
      if (!dragging || !target) return;
      draggedAt = performance.now();
      const el = target;
      let v = velocity * 16; // px per frame
      const step = () => {
        if (Math.abs(v) < 0.5) return stopGlide();
        el.scrollTop -= v;
        v *= FRICTION;
        glide = requestAnimationFrame(step);
      };
      if (Math.abs(v) > 2) glide = requestAnimationFrame(step);
    };
    // the end of a drag isn't a tap on whatever is under the finger
    const click = (e: MouseEvent) => {
      if (performance.now() - draggedAt < 400) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    root.addEventListener("touchstart", start, { passive: true });
    root.addEventListener("touchmove", move, { passive: true });
    root.addEventListener("touchend", end, { passive: true });
    root.addEventListener("touchcancel", end, { passive: true });
    root.addEventListener("click", click, true);
    return () => {
      stopGlide();
      root.removeEventListener("touchstart", start);
      root.removeEventListener("touchmove", move);
      root.removeEventListener("touchend", end);
      root.removeEventListener("touchcancel", end);
      root.removeEventListener("click", click, true);
    };
  }, []);
  return ref;
}
