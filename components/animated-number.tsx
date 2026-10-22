"use client";

import { animate, useMotionValue, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

// Counts from the previous to the new value; formatted text in every frame.
export function AnimatedNumber({ value, format, className }: { value: number; format: (v: number) => string; className?: string }) {
  const reduced = useReducedMotion();
  const motionValue = useMotionValue(0);
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    if (reduced) return;
    const controls = animate(motionValue, value, {
      duration: 0.9,
      ease: [0.2, 0.8, 0.2, 1],
      onUpdate: (latest) => setFrame(Math.round(latest)),
    });
    return () => controls.stop();
  }, [value, reduced, motionValue]);

  return (
    <span className={className} data-value={value}>
      {format(reduced ? value : frame)}
    </span>
  );
}
