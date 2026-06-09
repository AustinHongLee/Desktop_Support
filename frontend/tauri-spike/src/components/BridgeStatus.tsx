export function BridgeStatus({ error, message }: { error: string; message: string }) {
  if (!error && !message) {
    return null;
  }
  return <div className={`bridge-status ${error ? "error" : "ready"}`}>{error || message}</div>;
}
