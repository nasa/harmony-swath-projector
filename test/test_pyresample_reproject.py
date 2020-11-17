from unittest.mock import patch, ANY

from harmony.message import Message
from harmony.util import config

from swotrepr import HarmonyAdapter
from test.test_utils import TestBase, contains


class TestPyResampleReproject(TestBase):
    """A suite of tests to test SwotRepr, using pyresample and the valid input
    interpolation options. These tests will enforce REPR_MODE = 'pyresample',
    regardless of the actual value of REPR_MODE set in pymods.reproject.py

    """
    @patch('harmony.util.stage', return_value='https://example.com/data')
    def test_pyresample_interpolation(self, mock_stage):
        """Ensure SwotRepr will successfully complete when using pyresample and
        each specified interpolation.

        """
        valid_interpolations = ['bilinear', 'ewa', 'ewa-nn', 'near']

        for interpolation in valid_interpolations:
            with self.subTest(f'pyresample "{interpolation}" interpolation.'):
                test_data = Message({
                    'callback': 'https://example.com/callback',
                    'stagingLocation': 's3://example-bucket/example-path/',
                    'sources': [{
                        'granules': [{
                            'url': 'test/data/VOL2PSST_2017.nc',
                            'temporal': {
                                'start': '2020-01-01T00:00:00.000Z',
                                'end': '2020-01-02T00:00:00.000Z'
                            },
                            'bbox': [-180, -90, 180, 90]
                        }],
                    }],
                    'format': {'crs': 'EPSG:32603',
                               'interpolation': interpolation,
                               'width': 1000,
                               'height': 500}
                })

                reprojector = HarmonyAdapter(test_data, config=config(False))
                reprojector.invoke()

                mock_stage.assert_called_once_with(
                    contains('VOL2PSST_2017_repr.nc'),
                    'VOL2PSST_2017_regridded.nc',
                    'application/x-netcdf',
                    location='s3://example-bucket/example-path/',
                    logger=ANY)

                # Reset mock calls for next interpolation
                mock_stage.reset_mock()
