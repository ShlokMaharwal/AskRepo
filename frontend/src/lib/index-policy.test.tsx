import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Landing } from "@/components/askrepo/landing";

describe("public indexing restrictions", () => {
  it.each(["allowlist", "token"] as const)("keeps demo cards available in %s mode", (mode) => {
    const html = renderToStaticMarkup(
      <Landing onIndex={() => {}} onDemo={() => {}} busy={false} error="" indexingMode={mode} />,
    );
    const page = new DOMParser().parseFromString(html, "text/html");
    expect(page.querySelector("form button")?.hasAttribute("disabled")).toBe(true);
    expect(page.querySelectorAll(".demo-card")).toHaveLength(3);
    expect(
      [...page.querySelectorAll(".demo-card")].every((button) => !button.hasAttribute("disabled")),
    ).toBe(true);
    expect(page.querySelector('[role="note"]')?.textContent).toContain("demo");
  });
});
