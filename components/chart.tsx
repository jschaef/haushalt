"use client";

import { BarChart, PieChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";

echarts.use([BarChart, PieChart, GridComponent, TooltipComponent, CanvasRenderer]);

export type ChartOption = echarts.EChartsCoreOption;

// ECharts on a canvas that follows its container's size and the theme.
export function Chart({ option, className, label }: { option: ChartOption; className?: string; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (!ref.current) return;
    const instance = echarts.init(ref.current, resolvedTheme === "light" ? undefined : "dark", { renderer: "canvas" });
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, [resolvedTheme]);

  useEffect(() => {
    // high contrast: white, larger chart texts
    const contrast = resolvedTheme === "contrast" ? { textStyle: { color: "#ffffff", fontSize: 14 } } : {};
    chart.current?.setOption({ backgroundColor: "transparent", ...contrast, ...option }, { notMerge: true });
  }, [option, resolvedTheme]);

  return <div ref={ref} role="img" aria-label={label} className={className} />;
}
