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
        """Nominal (successful) reprojection for africa.nc"""
        test_data = {'granules': [{'local_filename': '/home/test/data/africa.nc'}],
                     'format': {'crs': 'EPSG:4326',
                                'interpolation': 'bilinear',
                                'scaleExtent': {'x': {'min': -20, 'max': 60},
                                                'y': {'min': 10, 'max': 35}}}}
        reprojector = HarmonyAdapter(test_data)
        granule = reprojector.message.granules[0]
        reprojector.invoke()

        completed_with_local_file.assert_called_once_with(contains('africa_repr.nc'), source_granule=granule, is_regridded=True, mime='application/x-netcdf')

        cleanup.assert_called_once()


if __name__ == '__main__':
    unittest.main()
