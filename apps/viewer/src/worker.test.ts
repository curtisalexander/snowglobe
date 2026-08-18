import { describe, expect, it } from "vitest";

import { stateFromMessage } from "./worker";

describe("database worker messages", () => {
  it("fails closed on unknown messages", () => {
    expect(stateFromMessage("ready")).toBe("ready");
    expect(stateFromMessage("failed")).toBe("failed");
    expect(stateFromMessage("contains-data")).toBe("starting");
  });
});
