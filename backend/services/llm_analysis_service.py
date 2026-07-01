from __future__ import annotations

import json
from collections import Counter
from typing import Any

import requests


MAX_HITS_FOR_PROMPT = 50
COUNT_FIELDS = ("cell_type", "disease", "tissue", "AgeGroup")


class LlmAnalysisError(RuntimeError):
    """Raised when the LLM provider cannot complete the analysis."""


def _clean_value(value: Any) -> Any:
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return round(value, 6)
    return value


def _count_values(hits: list[dict[str, Any]], field_name: str) -> list[dict[str, Any]]:
    counts = Counter(str(_clean_value(hit.get(field_name))) for hit in hits)
    return [{"value": value, "count": count} for value, count in counts.most_common()]


def _distance_stats(hits: list[dict[str, Any]]) -> dict[str, float | None]:
    distances = [float(hit["distance"]) for hit in hits if isinstance(hit.get("distance"), int | float)]
    if not distances:
        return {"min": None, "mean": None, "max": None}
    return {
        "min": round(min(distances), 6),
        "mean": round(sum(distances) / len(distances), 6),
        "max": round(max(distances), 6),
    }


def _summarize_cell(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "cell_id": _clean_value(cell.get("cell_id")),
        "dataset_id": _clean_value(cell.get("dataset_id")),
        "dataset_name": _clean_value(cell.get("dataset_name")),
        "cell_type": _clean_value(cell.get("cell_type")),
        "disease": _clean_value(cell.get("disease")),
        "AgeGroup": _clean_value(cell.get("AgeGroup")),
        "tissue": _clean_value(cell.get("tissue")),
    }


def _summarize_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": _clean_value(hit.get("rank")),
        "cell_id": _clean_value(hit.get("cell_id")),
        "dataset_id": _clean_value(hit.get("dataset_id")),
        "dataset_name": _clean_value(hit.get("dataset_name")),
        "distance": _clean_value(hit.get("distance")),
        "similarity": _clean_value(hit.get("similarity")),
        "cell_type": _clean_value(hit.get("cell_type")),
        "disease": _clean_value(hit.get("disease")),
        "AgeGroup": _clean_value(hit.get("AgeGroup")),
        "tissue": _clean_value(hit.get("tissue")),
    }


def build_analysis_context(search_result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(search_result, dict):
        raise ValueError("search_result must be an object")

    query_cell = search_result.get("query_cell")
    hits = search_result.get("hits")
    if not isinstance(query_cell, dict):
        raise ValueError("search_result.query_cell is required")
    if not isinstance(hits, list) or not hits:
        raise ValueError("search_result.hits must contain at least one result")

    prompt_hits = [hit for hit in hits[:MAX_HITS_FOR_PROMPT] if isinstance(hit, dict)]
    if not prompt_hits:
        raise ValueError("search_result.hits must contain result objects")

    query = search_result.get("query") if isinstance(search_result.get("query"), dict) else {}
    counts = {f"{field_name}_counts": _count_values(prompt_hits, field_name) for field_name in COUNT_FIELDS}
    distance_stats = _distance_stats(prompt_hits)

    return {
        "query": {
            "cell_id": _clean_value(query.get("cell_id") or query_cell.get("cell_id")),
            "dataset_id": _clean_value(query.get("dataset_id") or query_cell.get("dataset_id")),
            "index_id": _clean_value(query.get("index_id")),
            "top_k": _clean_value(query.get("top_k") or search_result.get("result_count") or len(hits)),
        },
        "query_cell": _summarize_cell(query_cell),
        "result_count": int(search_result.get("result_count") or len(hits)),
        "included_hit_count": len(prompt_hits),
        "truncated": len(hits) > len(prompt_hits),
        "distance_stats": distance_stats,
        "hits": [_summarize_hit(hit) for hit in prompt_hits],
        **counts,
    }


def build_input_summary(context: dict[str, Any]) -> dict[str, Any]:
    query_cell = context["query_cell"]
    return {
        "query_cell_id": query_cell.get("cell_id"),
        "dataset_id": query_cell.get("dataset_id"),
        "top_k": context["query"].get("top_k"),
        "result_count": context["result_count"],
        "included_hit_count": context["included_hit_count"],
        "cell_type_counts": context["cell_type_counts"],
        "disease_counts": context["disease_counts"],
        "tissue_counts": context["tissue_counts"],
        "AgeGroup_counts": context["AgeGroup_counts"],
        "distance_stats": context["distance_stats"],
        "truncated": context["truncated"],
    }


def build_prompt_blueprint(context: dict[str, Any], user_question: str | None = None) -> dict[str, Any]:
    query_cell = context["query_cell"]
    dominant_type = context["cell_type_counts"][0] if context["cell_type_counts"] else {"value": "-", "count": 0}
    distance_stats = context["distance_stats"]
    focus = user_question.strip() if user_question else "通用邻域解释"
    return {
        "title": "系统提示词增强分析结构",
        "user_focus": focus,
        "root": {
            "label": "用户分析问题",
            "value": focus,
        },
        "layers": [
            {
                "label": "检索对象",
                "value": str(query_cell.get("cell_id") or "-"),
                "detail": f"{query_cell.get('cell_type') or '-'} / {query_cell.get('dataset_id') or '-'}",
            },
            {
                "label": "邻域证据",
                "value": f"Top-K {context['result_count']}",
                "detail": f"主类型 {dominant_type['value']} x{dominant_type['count']}",
            },
            {
                "label": "距离约束",
                "value": f"mean {distance_stats.get('mean')}",
                "detail": f"min {distance_stats.get('min')} / max {distance_stats.get('max')}",
            },
            {
                "label": "模型解读任务",
                "value": "组成-距离-提示",
                "detail": "只基于检索结果和元数据生成 Markdown 报告",
            },
            {
                "label": "验证建议",
                "value": "后续实验/统计验证",
                "detail": "不输出临床诊断或输入外结论",
            },
        ],
    }


def build_messages(context: dict[str, Any], user_question: str | None = None) -> list[dict[str, str]]:
    prompt_blueprint = build_prompt_blueprint(context, user_question)
    system_prompt = (
        "你是单细胞向量检索结果辅助分析助手。你只能基于用户提供的 query cell、Top-K hits、"
        "距离/相似度和元数据字段进行解释；不要虚构基因表达、差异表达、文献事实、疾病因果或临床诊断。"
        "请用中文回答，结构清晰，适合科研人员快速阅读。输出必须是 Markdown，使用固定二级标题、短列表和加粗关键词，"
        "每个小节控制在 2-3 句话以内，避免冗长推理过程。你的输出会被前端转成可视化关系图，"
        "所以请显式写出“查询细胞 -> 邻域组成 -> 距离证据 -> 生物学提示 -> 下一步验证”的逻辑链。"
    )
    requested_focus = user_question.strip() if user_question else "无额外问题，请按通用检索结果进行解读。"
    user_payload = {
        "analysis_task": "解释单细胞 ANN Top-K 相似细胞检索结果",
        "required_sections": [
            "## 检索邻域概览",
            "## 主要相似细胞组成",
            "## 距离与相似度解读",
            "## 关键关系链",
            "## 可能的生物学提示",
            "## 局限性与下一步建议",
        ],
        "style_requirements": [
            "用 Markdown 二级标题组织内容",
            "关键字段和值可以使用加粗",
            "需要列点时使用短列表",
            "“关键关系链”必须用 3-5 条短列表表达，每条使用 A -> B -> C 的形式",
            "只基于输入元数据和距离统计组织逻辑，不要引入输入外证据",
            "不要输出模型思考过程或内部推理链",
        ],
        "user_question": requested_focus,
        "system_prompt_blueprint": prompt_blueprint,
        "context": context,
        "final_reminder": "结尾提醒：这是基于向量邻域和元数据的辅助解读，不是实验结论。",
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
    ]


class LlmAnalysisService:
    provider = "siliconflow"

    def analyze_search_result(
        self,
        search_result: dict[str, Any],
        config: dict[str, Any],
        user_question: str | None = None,
        enable_thinking: bool | None = None,
    ) -> dict[str, Any]:
        context = build_analysis_context(search_result)
        api_key = str(config.get("LLM_API_KEY") or "").strip()
        if not api_key:
            raise LlmAnalysisError("LLM API key is not configured; set SCANN_LLM_API_KEY")

        messages = build_messages(context, user_question)
        model = str(config.get("LLM_MODEL") or "Qwen/Qwen3-8B")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": float(config.get("LLM_TEMPERATURE") or 0.2),
            "max_tokens": int(config.get("LLM_MAX_TOKENS") or 600),
        }
        thinking_enabled = bool(config.get("LLM_ENABLE_THINKING")) if enable_thinking is None else bool(enable_thinking)
        if "qwen3" in model.lower() or thinking_enabled:
            payload["enable_thinking"] = thinking_enabled
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                str(config.get("LLM_API_URL")),
                headers=headers,
                json=payload,
                timeout=int(config.get("LLM_TIMEOUT_SECONDS") or 60),
            )
        except requests.Timeout as exc:
            raise LlmAnalysisError("LLM provider request timed out") from exc
        except requests.RequestException as exc:
            raise LlmAnalysisError(f"LLM provider request failed: {exc}") from exc

        if response.status_code >= 400:
            message = self._provider_error_message(response)
            raise LlmAnalysisError(f"LLM provider returned HTTP {response.status_code}: {message}")

        try:
            data = response.json()
            analysis = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmAnalysisError("LLM provider returned an invalid response format") from exc

        if not str(analysis).strip():
            raise LlmAnalysisError("LLM provider returned an empty analysis")

        return {
            "analysis": str(analysis).strip(),
            "provider": self.provider,
            "model": data.get("model") or model,
            "usage": data.get("usage") or {},
            "input_summary": build_input_summary(context),
            "prompt_blueprint": build_prompt_blueprint(context, user_question),
        }

    @staticmethod
    def _provider_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text[:300] or "empty error response"
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "provider error")
        if isinstance(error, str):
            return error
        if isinstance(payload, dict) and payload.get("message"):
            return str(payload["message"])
        return "provider error"


llm_analysis_service = LlmAnalysisService()
