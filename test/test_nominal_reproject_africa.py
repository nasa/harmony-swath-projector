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

    # TEST CASE: Nominal reprojection on a single band file
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_local_file')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_single_band_input(self, cleanup, completed_with_local_file):
        """Nominal (successful) reprojection for africa.nc"""
        test_data = {'granules': [{'local_filename': '/home/test/data/africa.nc'}],
            'format': {
                'crs': 'CRS:84',
                'interpolation': 'bilinear',
                'width': 1000, 'height': 500,
                'scaleExtent': {
                    'x': {'min': -20, 'max': 60},
                    'y': {'min': 10, 'max': 35}
                },
                # 'scaleSize': {'x': 1, 'y': 1}
            }
        }
        reprojector = HarmonyAdapter(test_data)
        reprojector.invoke()

        completed_with_local_file.assert_called_once_with(contains('africa_repr.nc'), 'africa.nc',
                                                          'application/x-netcdf')
        cleanup.assert_called_once()


if __name__ == '__main__':
    unittest.main()
