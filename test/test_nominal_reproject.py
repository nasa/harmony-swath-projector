import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


import unittest
from unittest.mock import patch

from reproject import HarmonyAdapter
from harmony import BaseHarmonyAdapter

from test_utils import contains, matches, TestBase



class TestNominalReproject(TestBase):

    # TEST CASE: No granules attribute
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_local_file')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_single_band_input(self, cleanup, completed_with_local_file):
        """Nominal (successful) reprojection"""
        test_data = {'granules' : [{'local_filename' : '/home/test/data/VNL2_oneBand.nc'}]}
        reprojector = HarmonyAdapter(test_data)
        reprojector.invoke()

        completed_with_local_file.assert_called_once_with(contains('VNL2_oneBand.nc'), 'VNL2_oneBand.nc', 'application/x-netcdf')
        cleanup.assert_called_once()

if __name__ == '__main__':
    unittest.main()