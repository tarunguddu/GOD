// GOD Coding Agent — VS Code extension.
//
// Thin client over the `god` CLI. It runs the deterministic critique on the
// active file and renders findings as native editor diagnostics, and shows the
// project-health report in an output channel. All analysis happens in the CLI;
// this extension only invokes it and presents results.

const vscode = require("vscode");
const { execFile } = require("child_process");
const path = require("path");

const SEVERITY = {
  CRITICAL: vscode.DiagnosticSeverity.Error,
  HIGH: vscode.DiagnosticSeverity.Error,
  MEDIUM: vscode.DiagnosticSeverity.Warning,
  LOW: vscode.DiagnosticSeverity.Information,
  INFO: vscode.DiagnosticSeverity.Hint,
};

function cliParts() {
  const cmd = vscode.workspace.getConfiguration("god").get("command", "god");
  const parts = cmd.split(/\s+/);
  return { bin: parts[0], baseArgs: parts.slice(1) };
}

function runCli(args, cwd) {
  const { bin, baseArgs } = cliParts();
  return new Promise((resolve) => {
    execFile(bin, [...baseArgs, ...args], { cwd, maxBuffer: 4 * 1024 * 1024 },
      (err, stdout, stderr) => resolve({ err, stdout, stderr }));
  });
}

function workspaceDir(uri) {
  const folder = vscode.workspace.getWorkspaceFolder(uri);
  return folder ? folder.uri.fsPath : path.dirname(uri.fsPath);
}

async function critique(doc, collection) {
  if (!doc || doc.languageId !== "python") return;
  const cwd = workspaceDir(doc.uri);
  const rel = path.relative(cwd, doc.uri.fsPath);
  const { stdout } = await runCli(["critique", rel, "--json"], cwd);
  let data;
  try { data = JSON.parse(stdout.trim().split("\n").pop()); }
  catch (e) { return; }

  const diags = (data.findings || []).map((f) => {
    const line = Math.max(0, (f.line || 1) - 1);
    const range = new vscode.Range(line, 0, line, 200);
    const d = new vscode.Diagnostic(
      range, `${f.rule}: ${f.message}`,
      SEVERITY[f.severity] ?? vscode.DiagnosticSeverity.Warning);
    d.source = "god";
    return d;
  });
  collection.set(doc.uri, diags);
}

async function health() {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders) { vscode.window.showWarningMessage("GOD: no workspace open."); return; }
  const cwd = folders[0].uri.fsPath;
  const channel = vscode.window.createOutputChannel("GOD Health");
  channel.clear();
  channel.show(true);
  channel.appendLine("Running GOD project-health analysis…");
  const { stdout, stderr } = await runCli(["health"], cwd);
  channel.appendLine(stdout || stderr || "(no output)");
}

function activate(context) {
  const collection = vscode.languages.createDiagnosticCollection("god");
  context.subscriptions.push(collection);

  context.subscriptions.push(
    vscode.commands.registerCommand("god.critiqueCurrentFile", () =>
      critique(vscode.window.activeTextEditor?.document, collection)),
    vscode.commands.registerCommand("god.health", health),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (vscode.workspace.getConfiguration("god").get("critiqueOnSave", true)) {
        critique(doc, collection);
      }
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
