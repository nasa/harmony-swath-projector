import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


import unittest
from unittest.mock import patch

from swotrepr import HarmonyAdapter
from test.harmony import BaseHarmonyAdapter
from test.test_utils import contains, matches, TestBase



class TestNominalReproject(TestBase):

    # TEST CASE: Nominal reprojection on a single band file
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_local_file')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_single_band_input(self, cleanup, completed_with_local_file):
        """Nominal (successful) reprojection"""
        test_data = {'granules': [{'local_filename': '/home/test/data/VNL2_oneBand.nc'}],
            'format': {
                'interpolation': 'ewa',
                'scaleExtent': {
                    'x': {'min':-160, 'max':-159},
                    'y': {'min':24, 'max':25}
                }
            }
        }
        reprojector = HarmonyAdapter(test_data)
        reprojector.invoke()

        completed_with_local_file.assert_called_once_with(contains('VNL2_oneBand_repr.nc'), 'VNL2_oneBand.nc', 'application/x-netcdf')
        cleanup.assert_called_once()

if __name__ == '__main__':
    unittest.main()