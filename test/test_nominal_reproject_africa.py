import unittest
from unittest.mock import patch, ANY

from harmony.message import Message
from harmony.util import config

from swotrepr import HarmonyAdapter
from test.test_utils import contains, TestBase


class TestNominalReproject(TestBase):

    # TEST CASE: Nominal reprojection on a single band file
    #
    @patch('harmony.util.stage', return_value='https://example.com/data')
    def test_single_band_input(self, mock_stage):
        """Nominal (successful) reprojection"""
        test_data = Message({
            'callback': 'https://example.com/callback',
            'stagingLocation': 's3://example-bucket/example-path/',
            'sources': [{
                'granules': [{
                    'url': 'test/data/africa.nc',
                    'temporal': {
                        'start': '2020-01-01T00:00:00.000Z',
                        'end': '2020-01-02T00:00:00.000Z'
                    },
                    'bbox': [-180, -90, 180, 90]
                }],
            }],
            'format': {'crs': 'EPSG:4326',
                       'interpolation': 'bilinear',
                       'scaleExtent': {'x': {'min': -20, 'max': 60},
                                       'y': {'min': 10, 'max': 35}}}
        })
        reprojector = HarmonyAdapter(test_data, config=config(False))
        reprojector.invoke()
        mock_stage.assert_called_once_with(
            contains('africa_repr.nc'),
            'africa_regridded.nc',
            'application/x-netcdf',
            location='s3://example-bucket/example-path/',
            logger=ANY)


if __name__ == '__main__':
    unittest.main()
