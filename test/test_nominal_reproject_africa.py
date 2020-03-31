from unittest.mock import patch
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


from swotrepr import HarmonyAdapter
from harmony import BaseHarmonyAdapter

from test_utils import contains, matches, TestBase


class TestNominalReproject(TestBase):

    # TEST CASE: Nominal reprojection on a single band file
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_local_file')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_single_band_input(self, cleanup, completed_with_local_file):
        """Nominal (successful) reprojection for africa.nc"""
        test_data = {'granules': [{'local_filename': '/home/test/data/africa.nc'}],
                     'format': {'crs': 'CRS:84',
                                'interpolation': 'bilinear',
                                'width': 1000,
                                'height': 500,
                                'scaleExtent': {'x': {'min': -20, 'max': 60},
                                                'y': {'min': 10, 'max': 35}}}}
        reprojector = HarmonyAdapter(test_data)
        granule = reprojector.message.granules[0]
        reprojector.invoke()

        completed_with_local_file.assert_called_once_with(contains('africa_repr.nc'), source_granule=granule, is_regridded=True, mime='application/x-netcdf')

        cleanup.assert_called_once()


if __name__ == '__main__':
    unittest.main()
