from unittest.mock import patch, ANY

from harmony.message import Message
from harmony.util import config

from swotrepr import HarmonyAdapter
from test.test_utils import download_side_effect, StringContains, TestBase

import netCDF4 as nc
from freezegun import freeze_time


@patch('harmony.util.stage', return_value='https://example.com/data')
@patch('swotrepr.download', side_effect=download_side_effect)
@freeze_time('2021-05-12T19:03:04.419341+00:00')
class TestSwotReprojectionTool(TestBase):
    """ A test class that will run the full SWOT Reprojection tool against a
        variety of input files and Harmony messages.

    """
    @classmethod
    def setUpClass(cls):
        """ Define class properties that do not need to be re-instantiated
            between tests.

        """
        cls.access_token = 'fake_token'
        cls.bounding_box = [-180, -90, 190, 90]
        cls.callback = 'http://example.com/callback'
        cls.mime_type = 'application/x-netcdf'
        cls.staging_location = 's3://example-bucket/example-path/'
        cls.temporal = {'start': '2020-01-01T00:00:00.000Z',
                        'end': '2020-01-02T00:00:00.000Z'}
        cls.history = ''

    def test_single_band_input(self, mock_download, mock_stage):
        """ Nominal (successful) reprojection of a single band input file. """
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': 'test/data/VNL2_oneBand.nc',
                    'temporal': self.temporal,
                    'bbox': self.bounding_box,
                }],
            }],
            'format': {'height': 500, 'width': 1000}
        })

        print('mock_download')
        print(mock_download)
        reprojector = HarmonyAdapter(test_data, config=config(False))
        reprojector.invoke()

        mock_download.assert_called_once_with('test/data/VNL2_oneBand.nc',
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('VNL2_oneBand_repr.nc'),
                                           'VNL2_oneBand_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

    def test_africa_input(self, mock_download, mock_stage):
        """ Nominal (successful) reprojection of test/data/africa.nc, using
            geographic coordinates, bilinear interpolation and specifying the
            extent of the target area grid.

        """
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': 'test/data/africa.nc',
                    'temporal': self.temporal,
                    'bbox': self.bounding_box,
                }],
            }],
            'format': {'crs': 'EPSG:4326',
                       'interpolation': 'bilinear',
                       'scaleExtent': {'x': {'min': -20, 'max': 60},
                                       'y': {'min': 10, 'max': 35}}}
        })

        reprojector = HarmonyAdapter(test_data, config=config(False))
        reprojector.invoke()

        nc_out_path = mock_stage.call_args[0][0]
        history_att_val = nc.Dataset(nc_out_path).getncattr("history")
        self.assertEqual(history_att_val,'2021-05-12T19:03:04.419341+00:00 sds/swot-reproject 0.9.0 {"crs": "EPSG:4326", "interpolation": "bilinear", "x_min": -20, "x_max": 60, "y_min": 10, "y_max": 35}')

        history_json_att_val = nc.Dataset(nc_out_path).getncattr("history_json")
        self.assertRegex(history_json_att_val,'[{\"$schema\": \"https:\/\/harmony.earthdata.nasa.gov\/schemas\/history\/0.1.0\/history\-v0.1.0.json\", \"time\": \"2021\-05\-12T19:03:04.419341+00:00\", \"program\": \"sds\/swot\-reproject\", \"version\": \"0.9.0\", \"parameters\": {\"crs\": \"EPSG:4326\", \"input_file\": \".*\/africa.nc\", \"interpolation\": \"bilinear\", \"x_min\": \-20, \"x_max\": 60, \"y_min\": 10, \"y_max\": 35}, \"derived_from\": \".*\/africa.nc\", \"program_ref\": \"https:\/\/cmr.uat.earthdata.nasa.gov\/search\/concepts\/S1237974711\-EEDTEST\"}]')

        mock_download.assert_called_once_with('test/data/africa.nc',
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('africa_repr.nc'),
                                           'africa_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

    def test_africa_input_with_histories(self, mock_download, mock_stage):
        """ Nominal (successful) reprojection of test/data/africa.nc, using
            geographic coordinates, bilinear interpolation and specifying the
            extent of the target area grid.
            Output file should succeed when input file already has history_json attribute.

        """
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': 'test/data/africa_hist.nc',
                    'temporal': self.temporal,
                    'bbox': self.bounding_box,
                }],
            }],
            'format': {'crs': 'EPSG:4326',
                       'interpolation': 'bilinear',
                       'scaleExtent': {'x': {'min': -20, 'max': 60},
                                       'y': {'min': 10, 'max': 35}}}
        })

        reprojector = HarmonyAdapter(test_data, config=config(False))
        reprojector.invoke()

        nc_out_path = mock_stage.call_args[0][0]
        history_att_val = nc.Dataset(nc_out_path).getncattr("history")
        self.assertEqual(history_att_val,'2021-05-13T13:06:32.059168+00:00 sds/swot-reproject 0.9.0 /var/folders/qf/b564t1md6xdfklc2yzyg00lc0000gp/T/tmpv5s6hux7/africa.nc\n2021-05-12T19:03:04.419341+00:00 sds/swot-reproject 0.9.0 {"crs": "EPSG:4326", "interpolation": "bilinear", "x_min": -20, "x_max": 60, "y_min": 10, "y_max": 35}')

        history_json_att_val = nc.Dataset(nc_out_path).getncattr("history_json")
        self.assertRegex(history_json_att_val,'[{\"$schema\": \"https:\/\/harmony.earthdata.nasa.gov\/schemas\/history\/0.1.0\/history\-v0.1.0.json\", \"time\": \"2021\-05\-12T19:03:04.419341+00:00\", \"program\": \"sds\/swot\-reproject\", \"version\": \"0.9.0\", \"parameters\": {\"crs\": \"EPSG:4326\", \"input_file\": \".*\/africa_hist.nc\", \"interpolation\": \"bilinear\", \"x_min\": \-20, \"x_max\": 60, \"y_min\": 10, \"y_max\": 35}, \"derived_from\": \".*\/africa_hist.nc\", \"program_ref\": \"https:\/\/cmr.uat.earthdata.nasa.gov\/search\/concepts\/S1237974711\-EEDTEST\"},{\"$schema\": \"https:\/\/harmony.earthdata.nasa.gov\/schemas\/history\/0.1.0\/history\-v0.1.0.json\", \"time\": \"2021\-05\-12T19:03:04.419341+00:00\", \"program\": \"sds\/swot\-reproject\", \"version\": \"0.9.0\", \"parameters\": {\"crs\": \"EPSG:4326\", \"input_file\": \".*\/africa_hist.nc\", \"interpolation\": \"bilinear\", \"x_min\": \-20, \"x_max\": 60, \"y_min\": 10, \"y_max\": 35}, \"derived_from\": \".*\/africa_hist.nc\", \"cf_history\": [\"2021\-05\-13T13:06:32.059168+00:00 sds/swot\-reproject 0.9.0 .*/africa_hist.nc\"]\"program_ref\": \"https:\/\/cmr.uat.earthdata.nasa.gov\/search\/concepts\/S1237974711\-EEDTEST\"}]')

        mock_download.assert_called_once_with('test/data/africa_hist.nc',
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('africa_hist_repr.nc'),
                                           'africa_hist_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

    def test_africa_input_with_History(self, mock_download, mock_stage):
        """ Nominal (successful) reprojection of test/data/africa.nc, using
            geographic coordinates, bilinear interpolation and specifying the
            extent of the target area grid.
            Output file should succeed when input file has global CF attribute "History'.

        """
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': 'test/data/africa_History.nc',
                    'temporal': self.temporal,
                    'bbox': self.bounding_box,
                }],
            }],
            'format': {'crs': 'EPSG:4326',
                       'interpolation': 'bilinear',
                       'scaleExtent': {'x': {'min': -20, 'max': 60},
                                       'y': {'min': 10, 'max': 35}}}
        })

        reprojector = HarmonyAdapter(test_data, config=config(False))
        reprojector.invoke()

        nc_out_path = mock_stage.call_args[0][0]
        history_att_val = nc.Dataset(nc_out_path).getncattr("History")
        self.assertEqual(history_att_val,'2021-06-03T20:00:00 Swathinator v0.0.1\n2021-05-12T19:03:04.419341+00:00 sds/swot-reproject 0.9.0 {"crs": "EPSG:4326", "interpolation": "bilinear", "x_min": -20, "x_max": 60, "y_min": 10, "y_max": 35}')

        history_json_att_val = nc.Dataset(nc_out_path).getncattr("history_json")
        self.assertRegex(history_json_att_val, '[{\"$schema\": \"https:\/\/harmony.earthdata.nasa.gov\/schemas\/history\/0.1.0\/history\-v0.1.0.json\", \"time\": \"2021\-05\-12T19:03:04.419341+00:00\", \"program\": \"sds\/swot\-reproject\", \"version\": \"0.9.0\", \"parameters\": {\"crs\": \"EPSG:4326\", \"input_file\": \".*\/africa.nc\", \"interpolation\": \"bilinear\", \"x_min\": \-20, \"x_max\": 60, \"y_min\": 10, \"y_max\": 35}, \"derived_from\": \".*\/africa.nc\", \"program_ref\": \"https:\/\/cmr.uat.earthdata.nasa.gov\/search\/concepts\/S1237974711\-EEDTEST\"}]')

        mock_download.assert_called_once_with('test/data/africa_History.nc',
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('africa_History_repr.nc'),
                                           'africa_History_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

    def test_single_band_input_default_crs(self, mock_download, mock_stage):
        """ Nominal (successful) reprojection of a single band input. This
            will default to using a geographic coordinate system, and use the
            Elliptically Weighted Average (EWA) interpolation method to derive
            the reprojected variables.

        """
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': 'test/data/VNL2_oneBand.nc',
                    'temporal': self.temporal,
                    'bbox': self.bounding_box,
                }],
            }],
            'format': {'interpolation': 'ewa',
                       'scaleExtent': {'x': {'min': -160, 'max': -159},
                                       'y': {'min': 24, 'max': 25}}}
        })

        reprojector = HarmonyAdapter(test_data, config=config(False))
        reprojector.invoke()

        mock_download.assert_called_once_with('test/data/VNL2_oneBand.nc',
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('VNL2_oneBand_repr.nc'),
                                           'VNL2_oneBand_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

    def test_single_band_input_reprojected_metres(self, mock_download, mock_stage):
        """ Nominal (successful) reprojection of the single band input file,
            specifying the UTM Zone 3N (EPSG:32603) target projection and the
            Elliptically Weighted Average, Nearest Neighbour (EWA-NN)
            interpolation algorithm to derive the reprojected variables.

            Note: This choice of target CRS is due to the location of the
            input data being near the Hawaiian islands.

        """
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': 'test/data/VNL2_oneBand.nc',
                    'temporal': self.temporal,
                    'bbox': self.bounding_box,
                }],
            }],
            'format': {
                'crs': 'EPSG:32603',
                'interpolation': 'ewa-nn',
                'scaleExtent': {'x': {'min': 0, 'max': 1500000},
                                'y': {'min': 2500000, 'max': 3300000}}
            }
        })
        reprojector = HarmonyAdapter(test_data, config=config(False))
        reprojector.invoke()

        mock_download.assert_called_once_with('test/data/VNL2_oneBand.nc',
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('VNL2_oneBand_repr.nc'),
                                           'VNL2_oneBand_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)
