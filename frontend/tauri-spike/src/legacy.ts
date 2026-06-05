import { invoke, isTauri } from "@tauri-apps/api/core";

export type LegacyWorkbench = "iso" | "cleanup" | "locks" | "shutdown";

export async function openLegacyWorkbench(workbench: LegacyWorkbench): Promise<string> {
  if (!isTauri()) {
    throw new Error("請用 Tauri 桌面版啟動，瀏覽器預覽不能叫出本機工作台。");
  }
  return invoke<string>("open_legacy_workbench", { workbench });
}
