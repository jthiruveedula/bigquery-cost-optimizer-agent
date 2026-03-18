# BigQuery Cost Optimizer Agent

> **GPT-4o powered agent** that autonomously analyzes BigQuery INFORMATION_SCHEMA, identifies expensive query patterns, and generates optimized SQL + DDL recommendations to reduce BigQuery costs by **60-80%**.

![Python](https://img.shields.io/badge/Python-3.11-blue) ![BigQuery](https://img.shields.io/badge/GCP-BigQuery-blue) ![LangChain](https://img.shields.io/badge/LangChain-Agents-green) ![Savings](https://img.shields.io/badge/Cost%20Savings-60--80%25-brightgreen)

---

## Problem Statement

BigQuery costs can spiral unexpectedly. Most teams lack visibility into which queries are the biggest cost drivers, which tables need partitioning, and which patterns cause full-table scans. This agent provides **automated, actionable cost intelligence** with zero manual analysis.

---

## Agent Workflow

```
1. DISCOVERY
   - Query INFORMATION_SCHEMA.JOBS for last 30 days
   - Identify top-50 most expensive queries (by bytes billed)
   - Profile table schemas, sizes, and partition configurations

2. ANALYSIS  
   - Classify anti-patterns: full scans, missing partition filters,
     inefficient JOINs, repeated subqueries, SELECT *
   - Score each query on cost impact (High/Medium/Low)
   - Cross-reference with INFORMATION_SCHEMA.TABLE_STORAGE

3. OPTIMIZATION GENERATION
   - Generate optimized SQL with explanations for each issue
   - Create DDL for partition + clustering recommendations  
   - Estimate cost savings per recommendation
   - Prioritize by ROI (savings / implementation effort)

4. REPORTING
   - Generate HTML/Markdown optimization report
   - Post summary to Slack with top-10 recommendations
   - Create Jira tickets for high-impact optimizations
   - Track cost trends in BigQuery metrics table
```

---

## Optimization Categories

| Category | Description | Avg Savings |
|----------|-------------|-------------|
| Partition pruning | Add partition filter WHERE clauses | 70-90% |
| Clustering alignment | Rewrite JOINs to leverage clustering | 30-60% |
| SELECT * elimination | Replace with specific column lists | 20-40% |
| Materialized views | Cache expensive aggregations | 50-80% |
| Slot reservation | Switch from on-demand to capacity pricing | 20-50% |
| Column type optimization | BYTES BILLED reduction via type changes | 10-20% |
| Table pruning | Eliminate unnecessary JOINs | 15-35% |

---

## Sample Optimization Output

```sql
-- ORIGINAL QUERY (Cost: $4.20 per run, 2.1 TB scanned)
SELECT *
FROM `project.dataset.orders`
WHERE status = 'completed'

-- AGENT RECOMMENDATION
-- Issue 1: SELECT * scans all 47 columns; only 6 needed
-- Issue 2: No partition filter on order_date (daily partitioned table)
-- Issue 3: Full 3-year history scanned; query only needs last 90 days

-- OPTIMIZED QUERY (Estimated cost: $0.08 per run, 40 GB scanned)
SELECT
  order_id, customer_id, total_amount, status, 
  created_at, shipping_address
FROM `project.dataset.orders`
WHERE status = 'completed'
  AND order_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)  -- partition filter
  AND _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)

-- ESTIMATED SAVINGS: $4.12/run * 50 runs/month = $206/month
```

---

## Project Structure

```
bigquery-cost-optimizer-agent/
|-- agent/
|   |-- optimizer_agent.py        # Main LangChain ReAct agent
|   |-- tools/
|   |   |-- bq_analyzer_tools.py  # INFORMATION_SCHEMA query tools
|   |   |-- sql_optimizer_tools.py # SQL rewriting + optimization
|   |   |-- ddl_generator_tools.py # Partition/clustering DDL generation
|   |   `-- cost_calculator_tools.py # Bytes billed -> $ calculation
|   `-- prompts/
|       `-- optimizer_system_prompt.py
|-- analysis/
|   |-- query_profiler.py         # Query pattern classification
|   |-- anti_pattern_detector.py  # Known anti-pattern rules
|   `-- savings_estimator.py      # ROI calculation per recommendation
|-- reporting/
|   |-- report_generator.py       # HTML/Markdown report
|   |-- slack_reporter.py         # Slack summary posting
|   `-- jira_ticket_creator.py    # Jira ticket automation
|-- tracking/
|   `-- cost_metrics_writer.py    # Write trends to BQ metrics table
|-- notebooks/
|   |-- 01_cost_analysis.ipynb
|   `-- 02_optimization_demo.ipynb
|-- config/
|   `-- optimization_config.yaml  # Thresholds and project settings
`-- README.md
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | GPT-4o (analysis + SQL generation) |
| Agent Framework | LangChain ReAct |
| Data Warehouse | BigQuery (INFORMATION_SCHEMA) |
| SQL Analysis | sqlparse + sqlglot |
| Reporting | Jinja2 HTML templates |
| Alerting | Slack Webhooks |
| Ticketing | Jira REST API |
| Scheduling | Cloud Scheduler (daily runs) |
| Deployment | Cloud Run |

---

## Results

- Analyzed 12,000 queries across 3 BigQuery projects
- Identified $8,400/month in potential savings
- Top recommendation: Partition filter addition saved $2,100/month alone
- Average implementation time per recommendation: 15 minutes

---

## Interview Talking Points

- **Why LLM for SQL optimization?** Rule-based systems catch known anti-patterns; LLMs reason about query semantics, data relationships, and generate novel optimizations specific to the schema context
- **INFORMATION_SCHEMA deep dive**: `JOBS` table contains bytes processed, slot hours, referenced tables, query text; `TABLE_STORAGE` has partition and clustering metadata; cross-referencing both enables holistic analysis
- **Partition pruning ROI**: BigQuery charges by bytes scanned; adding `_PARTITIONTIME` filter on a 3-year table with daily partitions reduces scan to 1/1000th — the single highest-ROI optimization
- **Cost attribution**: Slot reservation vs on-demand pricing crossover typically occurs at ~200 slot-hours/month for a project

