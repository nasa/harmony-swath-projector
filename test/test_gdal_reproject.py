import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import unittest
from unittest.mock import patch

from swotrepr import HarmonyAdapter
from harmony import BaseHarmonyAdapter

from test_utils import contains, TestBase


class TestGDALReproject(TestBase):

    # TEST CASE: GDAL reprojection on multi band file
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_local_file')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_multi_band_input(self, cleanup, completed_with_local_file):
        """GDAL reprojection"""
        test_data = {'granules': [{'local_filename': '/home/test/data/VOL2PSST_2017.nc'}],
            'format': {'crs': 'EPSG:32603', 'interpolation': 'near', 'width': 1000, 'height': 500,}}
        start = time.time()
        reprojector = HarmonyAdapter(test_data)
        granule = reprojector.message.granules[0]
        reprojector.invoke()
        end = time.time()
        print("Full time = " + str(end - start))
        completed_with_local_file.assert_called_once_with(
            contains('VOL2PSST_2017_repr.nc'),
            source_granule=granule,
            is_regridded=True,
            mime='application/x-netcdf'
        )
        cleanup.assert_called_once()


if __name__ == '__main__':
    unittest.main()
