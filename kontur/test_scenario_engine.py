import unittest
from court_lab import load_catalog
import scenario_engine as e
class WorkbookTests(unittest.TestCase):
 def test_all_69_match_workbook(self):
  rows=load_catalog();self.assertEqual(len(rows),69)
  for row in rows:
   s,_=e.initial_snapshot(row);v=e.calculate(row,s);x=e.ROWS[row['number']]
   for k,out in [('cost','additional_cost'),('avoided','avoided'),('residual','residual'),('balance','balance'),('net','net_rzd_effect'),('cash','cash_result')]:self.assertAlmostEqual(v[out],x['expected'][k],2)
   self.assertIsNone(v['actual_ai_savings'])
if __name__=='__main__':unittest.main()
