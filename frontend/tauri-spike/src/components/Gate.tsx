import { CircleAlert, CircleCheck, ScanLine } from "lucide-react";

export function Gate({ label, state }: { label: string; state: string }) {
  return (
    <div className={`gate ${state}`}>
      {state === "ready" ? <CircleCheck size={15} /> : state === "warn" ? <CircleAlert size={15} /> : <ScanLine size={15} />}
      <span>{label}</span>
    </div>
  );
}
