import { describe, expect, it } from "vitest";

import { stateFromMessage } from "./worker";

describe("database worker messages", () => {
  it("maps only lifecycle messages to visible states", () => {
    expect(stateFromMessage("ready")).toBe("ready");
    expect(stateFromMessage("published")).toBe("ready");
    expect(stateFromMessage("failed")).toBe("failed");
    expect(stateFromMessage("viewport")).toBe("starting");
    expect(stateFromMessage("contains-data")).toBe("starting");
  });
});
