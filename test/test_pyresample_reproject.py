import os
import sys
import time
import unittest
from unittest.mock import patch

from harmony import BaseHarmonyAdapter

from swotrepr import HarmonyAdapter
from test.test_utils import contains, TestBase


class TestPyResampleReproject(TestBase):
    """A suite of tests to test SwotRepr, using pyresample and the valid input
    interpolation options. These tests will enforce REPR_MODE = 'pyresample',
    regardless of the actual value of REPR_MODE set in pymods.reproject.py

    """
    @patch('pymods.reproject.REPR_MODE', 'pyresample')
    @patch.object(BaseHarmonyAdapter, 'completed_with_local_file')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_pyresample_interpolation(self, cleanup, completed_with_local_file):
        """Ensure SwotRepr will successfully complete when using pyresample and
        each specified interpolation.

        """
        valid_interpolations = ['bilinear', 'ewa', 'ewa-nn', 'near']

        for interpolation in valid_interpolations:
            with self.subTest(f'pyresample "{interpolation}" interpolation.'):
                test_data = {
                    'granules': [{
                        'local_filename': 'test/data/VOL2PSST_2017.nc'
                    }],
                    'format': {'crs': 'EPSG:32603',
                               'interpolation': interpolation,
                               'width': 1000,
                               'height': 500}
                }

                reprojector = HarmonyAdapter(test_data)
                granule = reprojector.message.granules[0]
                reprojector.invoke()

                completed_with_local_file.assert_called_once_with(
                    contains('VOL2PSST_2017_repr.nc'),
                    source_granule=granule,
                    is_regridded=True,
                    mime='application/x-netcdf'
                )
                cleanup.assert_called_once()

                # Reset mock calls for next interpolation
                completed_with_local_file.reset_mock()
                cleanup.reset_mock()
