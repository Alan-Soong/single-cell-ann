import React from "react";
import { createRoot } from "react-dom/client";
import { Activity, Database, GitBranch, Search } from "lucide-react";

import "./styles.css";

function StatusPanel({ title, icon, rows }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        {icon}
        <h2>{title}</h2>
      </div>
      <dl className="status-grid">
        {rows.map((row) => (
          <React.Fragment key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value ?? "-"}</dd>
          </React.Fragment>
        ))}
      </dl>
    </section>
  );
}

function App() {
  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Single-cell ANN Retrieval</p>
          <h1>单细胞 ANN 检索系统</h1>
        </div>
      </header>

      <section className="dashboard-grid">
        <StatusPanel
          title="数据集"
          icon={<Database size={20} />}
          rows={[
            { label: "状态", value: "待加载" },
            { label: "细胞数", value: "-" },
            { label: "向量维度", value: "-" },
          ]}
        />
        <StatusPanel
          title="索引"
          icon={<GitBranch size={20} />}
          rows={[
            { label: "状态", value: "待构建" },
            { label: "类型", value: "IVF_FLAT" },
            { label: "模式", value: "-" },
          ]}
        />
      </section>

      <section className="workspace">
        <div className="query-panel">
          <div className="panel-heading">
            <Search size={20} />
            <h2>检索</h2>
          </div>
          <p className="muted">下一步将接入数据加载、索引构建、查询表格和 UMAP 可视化。</p>
        </div>
        <div className="visual-panel">
          <div className="panel-heading">
            <Activity size={20} />
            <h2>UMAP</h2>
          </div>
          <div className="empty-plot">等待数据加载</div>
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
