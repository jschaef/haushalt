"use client";

import { MotionConfig } from "motion/react";
import { useTheme } from "next-themes";
import type { ReactNode } from "react";
import { isContrast } from "@/lib/themes";

// The low-vision modes switch all motion animations off, in addition
// to the user's operating system setting (reducedMotion="user").
export function MotionMode({ children }: { children: ReactNode }) {
  const { resolvedTheme } = useTheme();
  return <MotionConfig reducedMotion={isContrast(resolvedTheme) ? "always" : "user"}>{children}</MotionConfig>;
}
