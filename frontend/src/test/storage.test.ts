import { beforeEach, describe, expect, it } from "vitest";
import { migrateStorage } from "@/lib/storage";

const legacy = ["repo", "rag", ":"].join("");
beforeEach(() => localStorage.clear());

describe("AskRepo storage migration", () => {
  it("moves legacy keys once and preserves unrelated data", () => {
    localStorage.setItem(`${legacy}repos`, "saved");
    localStorage.setItem("other-app", "untouched");
    migrateStorage(localStorage);
    expect(localStorage.getItem("askrepo:repos")).toBe("saved");
    expect(localStorage.getItem(`${legacy}repos`)).toBeNull();
    expect(localStorage.getItem("other-app")).toBe("untouched");
    migrateStorage(localStorage);
    expect(localStorage.getItem("askrepo:repos")).toBe("saved");
  });

  it("preserves an existing AskRepo value", () => {
    localStorage.setItem(`${legacy}repos`, "old");
    localStorage.setItem("askrepo:repos", "new");
    migrateStorage(localStorage);
    expect(localStorage.getItem("askrepo:repos")).toBe("new");
    expect(localStorage.getItem(`${legacy}repos`)).toBeNull();
  });
});
