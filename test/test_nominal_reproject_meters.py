import os
import sys
import unittest
from unittest.mock import patch

from harmony import BaseHarmonyAdapter

from swotrepr import HarmonyAdapter
from test.test_utils import contains, matches, TestBase



class TestNominalReproject(TestBase):

    # TEST CASE: Nominal reprojection on a single band file
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_local_file')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_single_band_input(self, cleanup, completed_with_local_file):
        """Nominal (successful) reprojection"""
        test_data = {
            'granules': [{'local_filename': 'test/data/VNL2_oneBand.nc'}],
            'format': {
                'crs': 'EPSG:32603',
                'interpolation': 'ewa-nn',
                'scaleExtent': {'x': {'min': 0, 'max': 1500000},
                                'y': {'min': 2500000, 'max': 3300000}}
            }
        }
        reprojector = HarmonyAdapter(test_data)
        granule = reprojector.message.granules[0]
        reprojector.invoke()

        completed_with_local_file.assert_called_once_with(
            contains('VNL2_oneBand_repr.nc'),
            source_granule=granule,
            is_regridded=True,
            mime='application/x-netcdf')

        cleanup.assert_called_once()

if __name__ == '__main__':
    unittest.main()
