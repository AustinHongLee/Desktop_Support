import { ChevronDown } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

type NodeWorkbenchProps = {
  canvas: ReactNode;
  detail: ReactNode;
  drawer: ReactNode;
  drawerMeta: string;
  header: ReactNode;
};

export function NodeWorkbench({ canvas, detail, drawer, drawerMeta, header }: NodeWorkbenchProps) {
  return (
    <section style={styles.shell}>
      <div style={styles.header}>{header}</div>
      <div style={styles.main}>
        <div style={styles.canvasRegion}>{canvas}</div>
        <aside style={styles.detailRegion}>{detail}</aside>
      </div>
      <details style={styles.drawer}>
        <summary style={styles.drawerSummary}>
          <span>工程檢視</span>
          <em>{drawerMeta}</em>
          <ChevronDown size={15} />
        </summary>
        <div style={styles.drawerBody}>{drawer}</div>
      </details>
    </section>
  );
}

const styles = {
  canvasRegion: {
    minHeight: "min(72vh, 820px)",
    minWidth: 0,
  },
  detailRegion: {
    alignSelf: "stretch",
    background: "rgba(0,0,0,0.16)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 10,
    minHeight: 0,
    minWidth: 0,
    overflow: "auto",
    padding: 10,
  },
  drawer: {
    background: "rgba(0,0,0,0.12)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    minWidth: 0,
    overflow: "hidden",
  },
  drawerBody: {
    borderTop: "1px solid rgba(255,255,255,0.08)",
    minWidth: 0,
    padding: 10,
  },
  drawerSummary: {
    alignItems: "center",
    cursor: "pointer",
    display: "flex",
    gap: 10,
    justifyContent: "space-between",
    listStyle: "none",
    minWidth: 0,
    padding: "9px 11px",
  },
  header: {
    minWidth: 0,
  },
  main: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "minmax(0, 1fr) minmax(320px, 420px)",
    minWidth: 0,
  },
  shell: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    minWidth: 0,
  },
} satisfies Record<string, CSSProperties>;
