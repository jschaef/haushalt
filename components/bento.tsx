"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// A glass tile of the bento grid. Tiles fade and rise in one after another
// (index), which keeps the first paint calm.
export function Tile({
  children,
  className,
  index = 0,
  title,
  action,
  testId,
}: {
  children: ReactNode;
  className?: string;
  index?: number;
  title?: ReactNode;
  action?: ReactNode;
  testId?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.section
      data-testid={testId}
      initial={reduced ? false : { opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.45, delay: index * 0.05, ease: [0.2, 0.8, 0.2, 1] }}
      className={cn("glass flex flex-col gap-3 overflow-hidden rounded-3xl p-5", className)}
    >
      {(title || action) && (
        <header className="flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </motion.section>
  );
}

export function BentoGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid auto-rows-[minmax(8rem,auto)] grid-cols-2 gap-3 md:grid-cols-4 md:gap-4 xl:grid-cols-6", className)}>
      {children}
    </div>
  );
}
