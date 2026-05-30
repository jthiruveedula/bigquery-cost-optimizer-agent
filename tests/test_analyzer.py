import unittest
from src.optimizer.analyzer import QueryPatternAnalyzer

class TestQueryPatternAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = QueryPatternAnalyzer()

    def test_select_star(self):
        sql = "SELECT * FROM `project.dataset.table`"
        analysis = self.analyzer.analyze(sql, bytes_processed=100)
        self.assertTrue(analysis.has_select_star)
        self.assertIn("Replace SELECT * with explicit column list to reduce bytes scanned.", analysis.recommendations)

    def test_no_select_star(self):
        sql = "SELECT col1, col2 FROM `project.dataset.table`"
        analysis = self.analyzer.analyze(sql, bytes_processed=100)
        self.assertFalse(analysis.has_select_star)

    def test_cross_join(self):
        sql = "SELECT a.*, b.* FROM table_a a CROSS JOIN table_b b"
        analysis = self.analyzer.analyze(sql, bytes_processed=100)
        self.assertTrue(analysis.has_cross_join)
        self.assertIn("Detected CROSS JOIN. Ensure this is intentional as it can be extremely expensive.", analysis.recommendations)

    def test_missing_partition_filter(self):
        sql = "SELECT col1 FROM `project.dataset.table`"
        analysis = self.analyzer.analyze(sql, bytes_processed=2e9)
        self.assertTrue(analysis.missing_partition_filter)
        self.assertIn("Add partition filter (_PARTITIONTIME or partition column) to prune scanned data.", analysis.recommendations)

    def test_has_partition_filter(self):
        sql = "SELECT col1 FROM `project.dataset.table` WHERE _PARTITIONTIME > '2023-01-01'"
        analysis = self.analyzer.analyze(sql, bytes_processed=2e9)
        self.assertFalse(analysis.missing_partition_filter)

    def test_union_all_large(self):
        sql = "SELECT * FROM t1 UNION ALL SELECT * FROM t2 UNION ALL SELECT * FROM t3 UNION ALL SELECT * FROM t4 UNION ALL SELECT * FROM t5 UNION ALL SELECT * FROM t6"
        analysis = self.analyzer.analyze(sql, bytes_processed=60e9)
        self.assertTrue(analysis.has_union_all_on_large_tables)
        self.assertIn("Detected multiple UNION ALLs on large scans. Consider using wildcard tables or partitioning instead.", analysis.recommendations)

if __name__ == "__main__":
    unittest.main()
