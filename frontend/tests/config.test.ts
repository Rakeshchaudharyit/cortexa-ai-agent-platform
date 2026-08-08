import { describe, expect, it } from "vitest";

import { alignLoopbackApiHostname } from "@/lib/config";

describe("API base URL hostname alignment", () => {
  it("uses localhost for the API when the browser was opened on localhost", () => {
    expect(
      alignLoopbackApiHostname("http://127.0.0.1:18000", "localhost"),
    ).toBe("http://localhost:18000");
  });

  it("uses 127.0.0.1 for the API when the browser was opened on 127.0.0.1", () => {
    expect(
      alignLoopbackApiHostname("http://localhost:18000", "127.0.0.1"),
    ).toBe("http://127.0.0.1:18000");
  });

  it("does not rewrite production API hostnames", () => {
    expect(
      alignLoopbackApiHostname("https://api.cortexa.example", "localhost"),
    ).toBe("https://api.cortexa.example");
  });

  it("removes a trailing slash without changing an aligned hostname", () => {
    expect(
      alignLoopbackApiHostname("http://localhost:18000/", "localhost"),
    ).toBe("http://localhost:18000");
  });

  it("returns an invalid configured value unchanged instead of throwing", () => {
    expect(alignLoopbackApiHostname("not a url", "localhost")).toBe("not a url");
  });
});
