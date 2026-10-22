"use client";

import { MotionConfig } from "motion/react";
import { useTheme } from "next-themes";
import type { ReactNode } from "react";

// The high-contrast mode switches all motion animations off, in addition
// to the user's operating system setting (reducedMotion="user").
export function MotionMode({ children }: { children: ReactNode }) {
  const { resolvedTheme } = useTheme();
  return <MotionConfig reducedMotion={resolvedTheme === "contrast" ? "always" : "user"}>{children}</MotionConfig>;
}
