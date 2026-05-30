from __future__ import annotations
from dataclasses import dataclass

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
    has_cross_join: bool
    has_union_all_on_large_tables: bool
    recommendations: list[str]

    @property
    def tb_processed(self) -> float:
        return self.bytes_processed / 1e12
