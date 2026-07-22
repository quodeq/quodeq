import { describe, it, expect } from "vitest";
import { evaluationKeys, projectKeys, systemKeys, standardsKeys, settingsKeys } from "./queryKeys";

describe("query key factories", () => {
  it("evaluationKeys.evaluation returns the run-scope prefix", () => {
    expect(evaluationKeys.evaluation("job-1")).toEqual(["evaluation", "job-1"]);
  });

  it("evaluationKeys.status appends 'status' subkey", () => {
    expect(evaluationKeys.status("job-1")).toEqual(["evaluation", "job-1", "status"]);
  });

  it("evaluationKeys.findings appends 'findings'", () => {
    expect(evaluationKeys.findings("job-1")).toEqual(["evaluation", "job-1", "findings"]);
  });

  it("evaluationKeys.dimensions appends 'dimensions'", () => {
    expect(evaluationKeys.dimensions("job-1")).toEqual(["evaluation", "job-1", "dimensions"]);
  });

  it("projectKeys.project returns project-scope prefix, defaulting to the local source", () => {
    expect(projectKeys.project("p1")).toEqual(["project", "p1", "local"]);
  });

  it("projectKeys.project embeds an explicit source", () => {
    expect(projectKeys.project("p1", "shared")).toEqual(["project", "p1", "shared"]);
  });

  it("projectKeys.scores includes asOf when provided", () => {
    expect(projectKeys.scores("p1", "run-1")).toEqual(["project", "p1", "local", "scores", "run-1"]);
  });

  it("projectKeys.scores omits asOf when null", () => {
    expect(projectKeys.scores("p1", null)).toEqual(["project", "p1", "local", "scores", "latest"]);
  });

  it("projectKeys.scores embeds an explicit source", () => {
    expect(projectKeys.scores("p1", "run-1", "shared")).toEqual(["project", "p1", "shared", "scores", "run-1"]);
  });

  it("projectKeys.dashboard includes run when provided", () => {
    expect(projectKeys.dashboard("p1", "run-1")).toEqual(["project", "p1", "local", "dashboard", "run-1"]);
  });

  it("projectKeys.dashboard uses 'latest' when run is null", () => {
    expect(projectKeys.dashboard("p1", null)).toEqual(["project", "p1", "local", "dashboard", "latest"]);
  });

  it("projectKeys.dashboard embeds an explicit source", () => {
    expect(projectKeys.dashboard("p1", "run-1", "shared")).toEqual(["project", "p1", "shared", "dashboard", "run-1"]);
  });

  it("a local prefix does not match a shared key (cache isolation)", () => {
    const localPrefix = projectKeys.project("p1", "local");
    const sharedKey = projectKeys.dashboard("p1", "run-1", "shared");
    // Prefix match requires every element of localPrefix to equal the
    // corresponding element of sharedKey -- the source segment breaks it.
    const isPrefix = localPrefix.every((v, i) => v === sharedKey[i]);
    expect(isPrefix).toBe(false);
  });

  it("systemKeys.health is the global health key", () => {
    expect(systemKeys.health()).toEqual(["system", "health"]);
  });

  it("systemKeys.ollama is the global ollama key", () => {
    expect(systemKeys.ollama()).toEqual(["system", "ollama"]);
  });

  it("standardsKeys.list points to the standards list", () => {
    expect(standardsKeys.list()).toEqual(["standards", "list"]);
  });

  it("standardsKeys.library points to the standards library", () => {
    expect(standardsKeys.library()).toEqual(["standards", "library"]);
  });

  it("standardsKeys.cwes points to the CWE list", () => {
    expect(standardsKeys.cwes()).toEqual(["standards", "cwes"]);
  });

  it("settingsKeys.aiClients points to the AI client list", () => {
    expect(settingsKeys.aiClients()).toEqual(["settings", "aiClients"]);
  });

  it("settingsKeys.knownModels embeds the providerId", () => {
    expect(settingsKeys.knownModels("openai")).toEqual(["settings", "knownModels", "openai"]);
  });

  it("settingsKeys.ollamaModels is the local Ollama model list key", () => {
    expect(settingsKeys.ollamaModels()).toEqual(["settings", "ollamaModels"]);
  });
});
