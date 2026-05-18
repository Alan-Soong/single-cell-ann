import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:5000/api",
  timeout: 120000,
});

export async function getHealth() {
  const { data } = await api.get("/health");
  return data;
}

export async function loadDataset() {
  const { data } = await api.post("/datasets/load", {});
  return data;
}

export async function getCurrentDataset() {
  const { data } = await api.get("/datasets/current");
  return data;
}

export async function buildIndex() {
  const { data } = await api.post("/index/build", {});
  return data;
}

export async function getIndexStatus() {
  const { data } = await api.get("/index/status");
  return data;
}

export async function searchCells({ cellId, topK }) {
  const { data } = await api.post("/search", { cell_id: cellId, top_k: topK });
  return data;
}

export async function getVisualizationCells(limit = 5000) {
  const { data } = await api.get("/visualization/cells", { params: { limit } });
  return data;
}
