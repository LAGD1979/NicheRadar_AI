export const MAX_COMPARE = 8;
export const MIN_COMPARE = 2;

export function canSelect(selected: ReadonlySet<string>, id: string): boolean {
  return selected.has(id) || selected.size < MAX_COMPARE;
}

export function toggleSelection(selected: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(selected);
  if (next.has(id)) {
    next.delete(id);
  } else if (canSelect(selected, id)) {
    next.add(id);
  }
  return next;
}

export function isCompareReady(ids: readonly string[]): boolean {
  return ids.length >= MIN_COMPARE && ids.length <= MAX_COMPARE;
}

// Parámetro `ids` de la URL del comparador: separado por comas, sin repetidos ni vacíos.
export function parseIds(raw: string | null): string[] {
  if (!raw) return [];
  const unique = new Set(raw.split(",").map((s) => s.trim()).filter((s) => s.length > 0));
  return [...unique];
}
