"use client";
import { useEffect, useRef } from "react";
import { getGrade } from "@/lib/design";

interface Props {
  score: number;
  size?: number;
  showGrade?: boolean;
  /** false = layer not analysed (show neutral, not Critical F) */
  scored?: boolean;
}

export function ScoreRing({ score, size = 80, showGrade = true, scored = true }: Props) {
  const { color, letter, track } = getGrade(score, scored);
  const radius    = (size - 8) / 2;
  const circ      = 2 * Math.PI * radius;
  const fill      = scored ? (score / 100) * circ : 0;
  const dashRef   = useRef<SVGCircleElement>(null);

  useEffect(() => {
    const el = dashRef.current;
    if (!el) return;
    el.style.strokeDashoffset = String(circ);
    requestAnimationFrame(() => {
      el.style.transition = "stroke-dashoffset 0.8s ease";
      el.style.strokeDashoffset = String(circ - fill);
    });
  }, [circ, fill]);

  const cx = size / 2;
  const cy = size / 2;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle
        cx={cx} cy={cy} r={radius}
        fill="none" stroke={track} strokeWidth={6} opacity={0.45}
      />
      <circle
        ref={dashRef}
        cx={cx} cy={cy} r={radius}
        fill="none"
        stroke={color}
        strokeWidth={6}
        strokeDasharray={`${circ} ${circ}`}
        strokeDashoffset={circ}
        strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      <text
        x={cx} y={showGrade ? cy - 4 : cy + 5}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={size * 0.22}
        fontWeight="bold"
        fill={color}
      >
        {scored ? score : "—"}
      </text>
      {showGrade && (
        <text
          x={cx} y={cy + size * 0.15}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={size * 0.16}
          fill={color}
          opacity={0.85}
        >
          {letter}
        </text>
      )}
    </svg>
  );
}
