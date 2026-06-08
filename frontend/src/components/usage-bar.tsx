"use client";

type Props = {
  label: string;
  used: number;
  limit: number;
  formatter?: (n: number) => string;
};

export function UsageBar({ label, used, limit, formatter }: Props) {
  const fmt = formatter ?? ((n: number) => n.toString());
  const pct = limit === 0 ? 0 : Math.min(100, Math.round((used / limit) * 100));
  const over = used >= limit;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-600">
        <span>{label}</span>
        <span className={over ? "text-red-600 font-medium" : ""}>
          {fmt(used)} / {fmt(limit)}
        </span>
      </div>
      <div className="h-2 bg-gray-100 rounded overflow-hidden">
        <div
          className={`h-full ${over ? "bg-red-500" : "bg-blue-500"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return sec === 0 ? `${m}m` : `${m}m ${sec}s`;
}
