import { tableFromArrays } from "apache-arrow";
import { describe, expect, it } from "vitest";

import { createViewport, ViewportError } from "./viewport";

describe("bounded viewport", () => {
  it("returns only the requested rows and reports additional data", () => {
    const table = tableFromArrays({
      label: ["<script>CANARY</script>", "second", "third"],
      count: [1, 2, 3],
    });

    expect(createViewport(table, 2, 1024)).toEqual({
      columns: ["label", "count"],
      rows: [
        ["<script>CANARY</script>", "1"],
        ["second", "2"],
      ],
      hasMore: true,
    });
  });

  it("fails closed when the bounded viewport exceeds its byte budget", () => {
    const table = tableFromArrays({ value: ["VIEWPORT_CANARY"] });

    expect(() => createViewport(table, 1, 4)).toThrow(ViewportError);
  });
});
