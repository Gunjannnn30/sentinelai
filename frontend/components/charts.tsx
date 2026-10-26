"use client";

// Chart wrappers: every chart ships a visually-hidden <table> fallback so the
// data is reachable without the SVG, plus a toggle to show it openly.
import { useId, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";

export interface ChartColumn<T> {
  key: string;
  label: string;
  /** Value formatted for the fallback table. */
  format: (row: T) => string;
  /** Numeric value for the chart. null = gap. */
  value: (row: T) => number | null;
  color: string;
}

function ChartFrame<T>({
  title,
  rows,
  columns,
  chart,
  emptyLabel = "No data for this period.",
}: {
  title: string;
  rows: T[];
  columns: ChartColumn<T>[];
  chart: React.ReactNode;
  emptyLabel?: string;
}) {
  const [showTable, setShowTable] = useState(false);
  const captionId = useId();

  if (rows.length === 0) {
    return <p className="py-10 text-center text-sm text-muted-foreground">{emptyLabel}</p>;
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span id={captionId} className="sr-only">
          {title}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowTable((v) => !v)}
          aria-expanded={showTable}
        >
          {showTable ? "Hide data table" : "Show data table"}
        </Button>
      </div>
      <div className={showTable ? "hidden" : "sr-only"} aria-hidden={!showTable}>
        <table className="w-full text-sm">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr className="border-b">
              {columns.map((c) => (
                <th key={c.key} scope="col" className="px-2 py-1 text-left">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b last:border-0">
                {columns.map((c) => (
                  <td key={c.key} className="px-2 py-1">
                    {c.format(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={showTable ? "hidden" : ""} aria-hidden={showTable}>
        {chart}
      </div>
      {/* Always-present accessible fallback for screen readers when the SVG is shown. */}
      <div className="sr-only" aria-labelledby={captionId}>
        <table>
          <caption>{title}</caption>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {columns.map((c) => (
                  <th key={c.key} scope="row">
                    {c.label}: {c.format(row)}
                  </th>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function TimeseriesChart<T extends { date: string }>({
  title,
  rows,
  series,
}: {
  title: string;
  rows: T[];
  series: ChartColumn<T>[];
}) {
  const columns: ChartColumn<T>[] = [
    { key: "date", label: "Date", format: (r) => r.date, value: () => null, color: "" },
    ...series,
  ];
  return (
    <ChartFrame
      title={title}
      rows={rows}
      columns={columns}
      chart={
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={rows as unknown as Record<string, unknown>[]} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            {series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      }
    />
  );
}

export function BarChartView<T extends { key: string }>({
  title,
  rows,
  column,
  horizontal = false,
}: {
  title: string;
  rows: T[];
  column: ChartColumn<T>;
  horizontal?: boolean;
}) {
  const columns: ChartColumn<T>[] = [
    { key: "key", label: "Name", format: (r) => r.key, value: () => null, color: "" },
    column,
  ];
  const BarComp = BarChart;
  return (
    <ChartFrame
      title={title}
      rows={rows}
      columns={columns}
      chart={
        <ResponsiveContainer width="100%" height={240}>
          <BarComp
            data={rows as unknown as Record<string, unknown>[]}
            layout={horizontal ? "vertical" : "horizontal"}
            margin={{ top: 8, right: 8, bottom: 0, left: -16 }}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            {horizontal ? (
              <>
                <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                <YAxis type="category" dataKey="key" tick={{ fontSize: 11 }} width={120} />
              </>
            ) : (
              <>
                <XAxis dataKey="key" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
              </>
            )}
            <Tooltip />
            <Bar
              dataKey={column.key}
              name={column.label}
              fill={column.color}
              isAnimationActive={false}
            />
          </BarComp>
        </ResponsiveContainer>
      }
    />
  );
}
