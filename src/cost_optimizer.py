"""BigQuery Cost Optimizer Agent
AI-powered agent that analyzes query patterns, recommends partitioning,
clustering, materialized views, and slot reservations to reduce BQ costs.
"""

from __future__ import annotations
import re
import json
import logging
from dataclasses import dataclass
from typing import Any

from google.cloud import bigquery

logger = logging.getLogger(__name__)

COST_PER_TB = 5.0  # USD per TB scanned (on-demand)


@dataclass
class QueryAnalysis:
    query_id: str
    sql: str
    bytes_processed: int
    estimated_cost_usd: float
    tables_referenced: list[str]
    has_select_star: bool
    missing_partition_filter: bool
    missing_cluster_filter: bool
    recommendations: list[str]

    @property
    def tb_processed(self) -> float:
        return self.bytes_processed / 1e12


class QueryPatternAnalyzer:
    """Analyzes SQL patterns for cost inefficiencies."""

    SELECT_STAR_RE = re.compile(r"SELECT\s+\*", re.IGNORECASE)
    TABLE_RE = re.compile(r"FROM\s+`?([\w.]+)`?", re.IGNORECASE)

    def analyze(self, sql: str, bytes_processed: int, query_id: str = "") -> QueryAnalysis:
        recommendations = []
        has_select_star = bool(self.SELECT_STAR_RE.search(sql))
        if has_select_star:
            recommendations.append(
                "Replace SELECT * with explicit column list to reduce bytes scanned."
            )

        tables = self.TABLE_RE.findall(sql)
        missing_partition_filter = "_PARTITIONTIME" not in sql and "DATE(" not in sql and "partition_date" not in sql.lower()
        if missing_partition_filter and bytes_processed > 1e9:
            recommendations.append(
                "Add partition filter (_PARTITIONTIME or partition column) to prune scanned data."
            )

        missing_cluster_filter = bytes_processed > 5e9 and "WHERE" not in sql.upper()
        if missing_cluster_filter:
            recommendations.append(
                "Table may benefit from clustering. Add WHERE clause on high-cardinality columns."
            )

        if bytes_processed > 100e9:
            recommendations.append(
                "Consider creating a materialized view for this expensive recurring query."
            )

        cost = (bytes_processed / 1e12) * COST_PER_TB
        return QueryAnalysis(
            query_id=query_id,
            sql=sql,
            bytes_processed=bytes_processed,
            estimated_cost_usd=cost,
            tables_referenced=tables,
            has_select_star=has_select_star,
            missing_partition_filter=missing_partition_filter,
            missing_cluster_filter=missing_cluster_filter,
            recommendations=recommendations,
        )


class BigQueryCostOptimizerAgent:
    """AI-powered cost optimization agent for BigQuery."""

    def __init__(self, project_id: str, use_gemini: bool = True) -> None:
        self.project_id = project_id
        self.bq = bigquery.Client(project=project_id)
        self.analyzer = QueryPatternAnalyzer()
        self.use_gemini = use_gemini

    def fetch_expensive_queries(
        self, lookback_days: int = 7, limit: int = 50
    ) -> list[dict]:
        """Pull top expensive queries from INFORMATION_SCHEMA.JOBS."""
        sql = f"""
            SELECT
                job_id,
                query,
                total_bytes_processed,
                total_slot_ms,
                creation_time,
                user_email
            FROM `region-us`.INFORMATION_SCHEMA.JOBS
            WHERE
                creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {lookback_days} DAY)
                AND job_type = 'QUERY'
                AND state = 'DONE'
                AND total_bytes_processed IS NOT NULL
            ORDER BY total_bytes_processed DESC
            LIMIT {limit}
        """
        rows = list(self.bq.query(sql).result())
        return [
            {
                "job_id": r.job_id,
                "query": r.query,
                "bytes_processed": r.total_bytes_processed,
                "slot_ms": r.total_slot_ms,
                "user": r.user_email,
            }
            for r in rows
        ]

    def analyze_and_recommend(self, lookback_days: int = 7) -> dict:
        """Fetch expensive queries, analyze, and return optimization report."""
        queries = self.fetch_expensive_queries(lookback_days)
        analyses = []
        total_cost = 0.0
        total_savings = 0.0

        for q in queries:
            analysis = self.analyzer.analyze(
                sql=q["query"],
                bytes_processed=q["bytes_processed"],
                query_id=q["job_id"],
            )
            analyses.append(analysis)
            total_cost += analysis.estimated_cost_usd
            if analysis.recommendations:
                total_savings += analysis.estimated_cost_usd * 0.4  # estimated 40% savings

        top_issues = sorted(
            analyses, key=lambda a: a.estimated_cost_usd, reverse=True
        )[:10]

        report = {
            "summary": {
                "queries_analyzed": len(analyses),
                "total_estimated_cost_usd": round(total_cost, 4),
                "potential_savings_usd": round(total_savings, 4),
                "savings_pct": round((total_savings / total_cost * 100) if total_cost else 0, 1),
            },
            "top_expensive_queries": [
                {
                    "query_id": a.query_id,
                    "cost_usd": round(a.estimated_cost_usd, 4),
                    "tb_processed": round(a.tb_processed, 4),
                    "recommendations": a.recommendations,
                }
                for a in top_issues
            ],
        }

        if self.use_gemini:
            report["ai_summary"] = self._gemini_summary(report)

        return report

    def _gemini_summary(self, report: dict) -> str:
        """Use Gemini to generate a human-readable cost optimization summary."""
        try:
            import vertexai.generative_models as genai
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = (
                "You are a BigQuery cost optimization expert. "
                "Given this cost analysis report, write a 3-bullet executive summary "
                "with specific actionable recommendations:\n\n"
                + json.dumps(report["summary"], indent=2)
            )
            return model.generate_content(prompt).text
        except Exception as e:
            logger.warning("Gemini summary failed: %s", e)
            return ""

    def get_table_optimization_recommendations(self, table_ref: str) -> dict:
        """Analyze a specific table and recommend partitioning/clustering."""
        sql = f"""SELECT * FROM `{table_ref}` LIMIT 0"""
        job = self.bq.query(sql)
        job.result()
        table = self.bq.get_table(table_ref)

        recs = []
        if not table.time_partitioning and not table.range_partitioning:
            recs.append("Table has no partitioning. Add DATE/TIMESTAMP partitioning to reduce scan costs.")
        if not table.clustering_fields:
            recs.append("Table has no clustering. Add clustering on high-cardinality filter columns (user_id, region, etc.).")
        if table.num_bytes and table.num_bytes > 100e9:
            recs.append("Large table (>100GB). Consider BigQuery materialized views for frequent aggregations.")

        return {
            "table": table_ref,
            "size_gb": round((table.num_bytes or 0) / 1e9, 2),
            "partitioned": bool(table.time_partitioning or table.range_partitioning),
            "clustered": bool(table.clustering_fields),
            "recommendations": recs,
        }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    agent = BigQueryCostOptimizerAgent(project_id=args.project)
    report = agent.analyze_and_recommend(lookback_days=args.days)
    print(json.dumps(report, indent=2))

