import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Canonical shadcn/ui helper — merges Tailwind classes, deduplicates
 * conflicts (e.g. `p-2 p-4` → `p-4`).
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
