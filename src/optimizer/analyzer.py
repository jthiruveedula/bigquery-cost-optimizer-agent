from __future__ import annotations
import logging
import sqlglot
from sqlglot import exp, parse_one
from .models import QueryAnalysis

logger = logging.getLogger(__name__)
COST_PER_TB = 5.0

class QueryPatternAnalyzer:
    """Analyzes SQL patterns for cost inefficiencies using sqlglot."""

    def analyze(self, sql: str, bytes_processed: int, query_id: str = "") -> QueryAnalysis:
        recommendations = []
        tables_referenced = []
        has_select_star = False
        has_cross_join = False
        has_union_all_on_large_tables = False

        try:
            expression = parse_one(sql, read="bigquery")

            # Extract tables
            for table in expression.find_all(exp.Table):
                tables_referenced.append(table.sql())
            tables_referenced = list(set(tables_referenced))

            # Detect SELECT *
            for select in expression.find_all(exp.Select):
                for projection in select.expressions:
                    if isinstance(projection, exp.Star) or (isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star)):
                        has_select_star = True
                        break
                if has_select_star:
                    break

            if has_select_star:
                recommendations.append(
                    "Replace SELECT * with explicit column list to reduce bytes scanned."
                )

            # Detect Cross Joins
            for join in expression.find_all(exp.Join):
                if join.args.get("kind") == "CROSS":
                    has_cross_join = True
                    recommendations.append(
                        "Detected CROSS JOIN. Ensure this is intentional as it can be extremely expensive."
                    )
                    break

            # Detect UNION ALL on many tables
            unions = list(expression.find_all(exp.Union))
            if len(unions) >= 5 and bytes_processed > 50e9:
                has_union_all_on_large_tables = True
                recommendations.append(
                    "Detected multiple UNION ALLs on large scans. Consider using wildcard tables or partitioning instead."
                )

            # Analyze WHERE clause
            where_clause = expression.find(exp.Where)
            where_sql = where_clause.sql().upper() if where_clause else ""

            partition_keywords = ["_PARTITIONTIME", "_PARTITIONDATE", "PARTITION_DATE", "DATE("]
            missing_partition_filter = not any(kw in where_sql for kw in partition_keywords)

            if missing_partition_filter and bytes_processed > 1e9:
                recommendations.append(
                    "Add partition filter (_PARTITIONTIME or partition column) to prune scanned data."
                )

            missing_cluster_filter = bytes_processed > 5e9 and not where_clause
            if missing_cluster_filter:
                recommendations.append(
                    "Table may benefit from clustering. Add WHERE clause on high-cardinality columns."
                )

        except Exception as e:
            logger.warning("Failed to parse SQL with sqlglot: %s", e)
            missing_partition_filter = "_PARTITIONTIME" not in sql.upper()
            has_select_star = "*" in sql
            has_cross_join = "CROSS JOIN" in sql.upper()
            has_union_all_on_large_tables = "UNION ALL" in sql.upper() and sql.upper().count("UNION ALL") >= 5

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
            tables_referenced=tables_referenced,
            has_select_star=has_select_star,
            missing_partition_filter=missing_partition_filter,
            missing_cluster_filter=missing_cluster_filter,
            has_cross_join=has_cross_join,
            has_union_all_on_large_tables=has_union_all_on_large_tables,
            recommendations=recommendations,
        )
