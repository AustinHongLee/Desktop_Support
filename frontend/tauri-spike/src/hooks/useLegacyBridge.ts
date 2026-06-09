import { useState } from "react";
import { openLegacyWorkbench, type LegacyWorkbench } from "../legacy";

export interface LegacyBridgeState {
  busy: boolean;
  error: string;
  launch: () => Promise<void>;
  message: string;
}

export function useLegacyBridge(workbench: LegacyWorkbench): LegacyBridgeState {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function launch() {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await openLegacyWorkbench(workbench);
      setMessage("已送出開啟請求");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, launch, message };
}
