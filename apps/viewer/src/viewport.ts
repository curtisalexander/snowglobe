export type Viewport = {
  columns: string[];
  rows: Array<Array<string | null>>;
  hasMore: boolean;
};

type ViewportTable = {
  numRows: number;
  numCols: number;
  schema: { fields: ArrayLike<{ name: string }> };
  getChildAt(index: number): { get(index: number): unknown } | null;
};

export class ViewportError extends Error {
  constructor() {
    super("Invalid result viewport");
    this.name = "ViewportError";
  }
}

export function createViewport(
  table: ViewportTable,
  rowLimit: number,
  maximumBytes: number,
): Viewport {
  if (
    !Number.isSafeInteger(rowLimit) ||
    rowLimit <= 0 ||
    !Number.isSafeInteger(maximumBytes) ||
    maximumBytes <= 0 ||
    table.numRows > rowLimit + 1
  ) {
    throw new ViewportError();
  }

  const encoder = new TextEncoder();
  let bytes = 0;
  const account = (value: string): string => {
    bytes += encoder.encode(value).byteLength;
    if (bytes > maximumBytes) throw new ViewportError();
    return value;
  };
  const columns = Array.from(table.schema.fields, (field) => account(field.name));
  const rowCount = Math.min(table.numRows, rowLimit);
  const rows: Array<Array<string | null>> = [];

  for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
    const row: Array<string | null> = [];
    for (let columnIndex = 0; columnIndex < table.numCols; columnIndex += 1) {
      const value = table.getChildAt(columnIndex)?.get(rowIndex);
      row.push(value === null || value === undefined ? null : account(formatCell(value)));
    }
    rows.push(row);
  }
  return { columns, rows, hasMore: table.numRows > rowLimit };
}

function formatCell(value: unknown): string {
  if (value instanceof Uint8Array) {
    return Array.from(value, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  if (value instanceof Date) return value.toISOString();
  return String(value);
}
