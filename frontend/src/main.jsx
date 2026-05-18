import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { GridComponent, TooltipComponent } from "echarts/components";
import { use as useEcharts, init as initEcharts } from "echarts/core";
import { ScatterChart } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";
import { Activity, AlertCircle, Database, GitBranch, LoaderCircle, Play, RefreshCw, Search } from "lucide-react";

import "./styles.css";
import {
  buildIndex,
  getCurrentDataset,
  getHealth,
  getIndexStatus,
  getVisualizationCells,
  loadDataset,
  searchCells,
} from "./api/client";

useEcharts([GridComponent, TooltipComponent, ScatterChart, CanvasRenderer]);

const palette = [
  "#2563eb",
  "#dc2626",
  "#059669",
  "#d97706",
  "#7c3aed",
  "#0891b2",
  "#be123c",
  "#4d7c0f",
  "#9333ea",
  "#0f766e",
];

function getErrorMessage(error) {
  return error?.response?.data?.message || error?.response?.data?.error || error?.message || "请求失败";
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  return Number(value).toLocaleString("zh-CN");
}

function StatusBadge({ value, tone = "neutral" }) {
  return <span className={`status-badge ${tone}`}>{value}</span>;
}

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

function UmapChart({ points, queryCell, hits }) {
  const ref = useRef(null);

  const hitIds = useMemo(() => new Set((hits || []).map((hit) => hit.cell_id)), [hits]);

  useEffect(() => {
    if (!ref.current) return;
    const chart = initEcharts(ref.current);
    const colorByType = new Map();
    const data = (points || []).map((point) => {
      if (!colorByType.has(point.cell_type)) {
        colorByType.set(point.cell_type, palette[colorByType.size % palette.length]);
      }
      return {
        value: [point.x, point.y],
        name: point.cell_id,
        cell_type: point.cell_type,
        itemStyle: {
          color: colorByType.get(point.cell_type),
          opacity: hitIds.has(point.cell_id) ? 0.95 : 0.48,
        },
      };
    });

    const hitData = (hits || [])
      .filter((hit) => hit.umap)
      .map((hit) => ({
        value: hit.umap,
        name: hit.cell_id,
        cell_type: hit.cell_type,
      }));

    const queryData = queryCell?.umap
      ? [
          {
            value: queryCell.umap,
            name: queryCell.cell_id,
            cell_type: queryCell.cell_type,
          },
        ]
      : [];

    chart.setOption({
      animation: false,
      grid: { left: 8, right: 8, top: 8, bottom: 8 },
      tooltip: {
        trigger: "item",
        formatter: (params) => {
          const dataItem = params.data || {};
          return `${dataItem.name}<br/>${dataItem.cell_type || "-"}`;
        },
      },
      xAxis: { type: "value", show: false },
      yAxis: { type: "value", show: false },
      series: [
        {
          name: "cells",
          type: "scatter",
          symbolSize: 5,
          data,
          large: true,
        },
        {
          name: "top-k",
          type: "scatter",
          symbolSize: 12,
          data: hitData,
          itemStyle: { color: "#f97316", borderColor: "#7c2d12", borderWidth: 1.5 },
          z: 3,
        },
        {
          name: "query",
          type: "scatter",
          symbol: "diamond",
          symbolSize: 18,
          data: queryData,
          itemStyle: { color: "#111827", borderColor: "#ffffff", borderWidth: 2 },
          z: 4,
        },
      ],
    });

    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [points, queryCell, hits, hitIds]);

  if (!points?.length) {
    return <div className="empty-plot">未加载</div>;
  }

  return <div ref={ref} className="chart" />;
}

function App() {
  const [health, setHealth] = useState(null);
  const [dataset, setDataset] = useState(null);
  const [indexStatus, setIndexStatus] = useState(null);
  const [visPoints, setVisPoints] = useState([]);
  const [queryCellId, setQueryCellId] = useState("");
  const [topK, setTopK] = useState(10);
  const [searchResult, setSearchResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function refreshStatus() {
    const [healthData, datasetData, indexData] = await Promise.all([getHealth(), getCurrentDataset(), getIndexStatus()]);
    setHealth(healthData);
    setDataset(datasetData);
    setIndexStatus(indexData);
    if (datasetData.loaded && !visPoints.length) {
      const visData = await getVisualizationCells();
      setVisPoints(visData.points);
    }
  }

  useEffect(() => {
    refreshStatus().catch((err) => setError(getErrorMessage(err)));
  }, []);

  async function runAction(name, action) {
    setBusy(name);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function handleLoadDataset() {
    await runAction("load", async () => {
      const data = await loadDataset();
      setDataset(data);
      setQueryCellId(data.sample_cell_ids?.[0] || "");
      const visData = await getVisualizationCells();
      setVisPoints(visData.points);
      await refreshStatus();
    });
  }

  async function handleBuildIndex() {
    await runAction("index", async () => {
      const data = await buildIndex();
      setIndexStatus(data);
    });
  }

  async function handleSearch(event) {
    event.preventDefault();
    await runAction("search", async () => {
      const result = await searchCells({ cellId: queryCellId, topK });
      setSearchResult(result);
    });
  }

  const datasetTone = dataset?.loaded ? "good" : "neutral";
  const indexTone = indexStatus?.ready ? "good" : indexStatus?.status === "error" ? "bad" : "neutral";
  const faissMode = health?.faiss?.mode || indexStatus?.mode || "-";

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Single-cell ANN Retrieval</p>
          <h1>单细胞 ANN 检索系统</h1>
        </div>
        <button className="ghost-button" onClick={() => runAction("refresh", refreshStatus)} disabled={Boolean(busy)}>
          <RefreshCw size={18} className={busy === "refresh" ? "spin" : ""} />
          刷新
        </button>
      </header>

      {error ? (
        <div className="error-banner">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      ) : null}

      <section className="dashboard-grid">
        <StatusPanel
          title="数据集"
          icon={<Database size={20} />}
          rows={[
            { label: "状态", value: <StatusBadge value={dataset?.status || "not_loaded"} tone={datasetTone} /> },
            { label: "细胞数", value: formatNumber(dataset?.cell_count) },
            { label: "向量维度", value: dataset?.vector_dim },
            { label: "示例细胞", value: dataset?.sample_cell_ids?.[0] },
          ]}
        />
        <StatusPanel
          title="索引"
          icon={<GitBranch size={20} />}
          rows={[
            { label: "状态", value: <StatusBadge value={indexStatus?.status || "not_built"} tone={indexTone} /> },
            { label: "类型", value: indexStatus?.index_type || "IVF_FLAT" },
            { label: "模式", value: faissMode },
            { label: "nprobe", value: indexStatus?.nprobe || "-" },
          ]}
        />
      </section>

      <section className="workspace">
        <div className="query-panel">
          <div className="panel-heading">
            <Search size={20} />
            <h2>检索</h2>
          </div>
          <div className="button-row">
            <button onClick={handleLoadDataset} disabled={Boolean(busy)}>
              {busy === "load" ? <LoaderCircle size={18} className="spin" /> : <Database size={18} />}
              加载数据
            </button>
            <button onClick={handleBuildIndex} disabled={Boolean(busy) || !dataset?.loaded}>
              {busy === "index" ? <LoaderCircle size={18} className="spin" /> : <GitBranch size={18} />}
              构建索引
            </button>
          </div>

          <form className="search-form" onSubmit={handleSearch}>
            <label>
              细胞 ID
              <input value={queryCellId} onChange={(event) => setQueryCellId(event.target.value)} />
            </label>
            <label>
              Top-K
              <input
                type="number"
                min="1"
                max="100"
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
              />
            </label>
            <button type="submit" disabled={Boolean(busy) || !queryCellId || !indexStatus?.ready}>
              {busy === "search" ? <LoaderCircle size={18} className="spin" /> : <Play size={18} />}
              查询
            </button>
          </form>

          <div className="metric-strip">
            <div>
              <span>耗时</span>
              <strong>{searchResult ? `${searchResult.query_time_ms} ms` : "-"}</strong>
            </div>
            <div>
              <span>结果数</span>
              <strong>{searchResult?.result_count ?? "-"}</strong>
            </div>
          </div>

          <div className="result-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Cell ID</th>
                  <th>Type</th>
                  <th>Distance</th>
                </tr>
              </thead>
              <tbody>
                {(searchResult?.hits || []).map((hit) => (
                  <tr key={hit.cell_id}>
                    <td>{hit.rank}</td>
                    <td>{hit.cell_id}</td>
                    <td>{hit.cell_type}</td>
                    <td>{hit.distance.toFixed(4)}</td>
                  </tr>
                ))}
                {!searchResult?.hits?.length ? (
                  <tr>
                    <td colSpan="4" className="empty-cell">
                      无结果
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
        <div className="visual-panel">
          <div className="panel-heading">
            <Activity size={20} />
            <h2>UMAP</h2>
          </div>
          <UmapChart points={visPoints} queryCell={searchResult?.query_cell} hits={searchResult?.hits || []} />
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
