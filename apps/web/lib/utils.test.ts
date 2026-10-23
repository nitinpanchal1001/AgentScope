import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("merges conflicting Tailwind utilities", () => {
    expect(cn("px-2 text-sm", "px-4")).toContain("px-4");
    expect(cn("px-2 text-sm", "px-4")).not.toContain("px-2");
  });
});
