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

  it("projectKeys.project returns project-scope prefix", () => {
    expect(projectKeys.project("p1")).toEqual(["project", "p1"]);
  });

  it("projectKeys.scores includes asOf when provided", () => {
    expect(projectKeys.scores("p1", "run-1")).toEqual(["project", "p1", "scores", "run-1"]);
  });

  it("projectKeys.scores omits asOf when null", () => {
    expect(projectKeys.scores("p1", null)).toEqual(["project", "p1", "scores", "latest"]);
  });

  it("projectKeys.dashboard includes run when provided", () => {
    expect(projectKeys.dashboard("p1", "run-1")).toEqual(["project", "p1", "dashboard", "run-1"]);
  });

  it("projectKeys.dashboard uses 'latest' when run is null", () => {
    expect(projectKeys.dashboard("p1", null)).toEqual(["project", "p1", "dashboard", "latest"]);
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
