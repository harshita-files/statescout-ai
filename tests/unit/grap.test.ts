import { describe, it, expect } from "bun:test";
import { createNode } from "../../packages/graph-core/index";

describe("graph-core", () => {
  it("creates a node with id", () => {
    const node = createNode("harshita-files");
    expect(node).toEqual({ id: "harshita-files" });
  });
});