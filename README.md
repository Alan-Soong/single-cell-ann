# 单细胞 ANN 检索系统

本项目是软件工程课程中期版本，实现一个前后端分离的单细胞相似细胞检索 Web 应用。

中期目标：

- 读取 `data/liver.h5ad`。
- 使用 `obsm["X_pca"]` 作为检索向量。
- 使用 FAISS IVF_FLAT 构建 ANN 索引。
- 支持按细胞 ID 查询 Top-K 相似细胞。
- 返回查询耗时、细胞类型、疾病、年龄组、组织和 UMAP 坐标。
- 前端展示数据集状态、索引状态、Top-K 表格和 UMAP 散点图。

## 环境

优先创建 GPU FAISS 环境：

```powershell
conda env create -f environment.yml
conda activate single-cell-ann
python -c "import faiss; print(faiss.__version__)"
```

如果 `faiss-gpu` 在本机求解失败，可以将 `environment.yml` 中的 `faiss-gpu` 替换为 `faiss-cpu` 后重新创建环境。后端代码会自动检测 GPU FAISS 能力；不可用时会使用 CPU FAISS。

## 数据

本地数据文件放在：

```text
data/liver.h5ad
```

该文件较大，不提交到 Git 仓库。数据字段说明见 `data/数据说明.md`。

## 运行

后端：

```powershell
conda activate single-cell-ann
python -m backend.app
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

默认后端地址为 `http://127.0.0.1:5000`，前端开发地址为 `http://127.0.0.1:5173`。

## 中期演示流程

1. 启动后端和前端。
2. 点击“加载数据”。
3. 点击“构建索引”。
4. 使用页面给出的示例细胞 ID 或手动输入细胞 ID。
5. 设置 Top-K 并执行查询。
6. 查看结果表格、查询耗时和 UMAP 高亮点。
