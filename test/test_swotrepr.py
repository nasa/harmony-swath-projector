from datetime import datetime
from os import makedirs
from shutil import copy, rmtree
from unittest.mock import Mock, patch, ANY
import json

from netCDF4 import Dataset

from harmony.message import Message
from harmony.util import config

from swotrepr import HarmonyAdapter
from test.test_utils import download_side_effect, StringContains, TestBase


@patch('pymods.nc_merge.datetime')
@patch('harmony.util.stage', return_value='https://example.com/data')
@patch('swotrepr.download', side_effect=download_side_effect)
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
        cls.tmp_dir = 'test/temp'

    def setUp(self):
        """ Set properties of tests that need to be re-created every test. """
        makedirs(self.tmp_dir)
        copy('test/data/africa.nc', self.tmp_dir)

    def tearDown(self):
        """ Perform per-test teardown operations. """
        rmtree(self.tmp_dir)

    def get_provenance(self, file_path):
        """ Utility method to retrieve `history`, `History` and `history_json`
            global attributes from a test output file.

        """
        with Dataset(file_path, 'r') as dataset:
            history = getattr(dataset, 'history', None)
            history_uppercase = getattr(dataset, 'History', None)
            history_json = getattr(dataset, 'history_json', None)

        return history, history_uppercase, history_json

    def test_single_band_input(self, mock_download, mock_stage, mock_datetime):
        """ Nominal (successful) reprojection of a single band input file. """
        input_file_path = 'test/data/VNL2_oneBand.nc'
        mock_datetime.utcnow = Mock(return_value=datetime(2021, 5, 12, 19, 3, 4))
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': input_file_path,
                    'temporal': self.temporal,
                    'bbox': self.bounding_box,
                }],
            }],
            'format': {'height': 500, 'width': 1000}
        })

        reprojector = HarmonyAdapter(test_data, config=config(False))
        reprojector.invoke()

        mock_download.assert_called_once_with(input_file_path,
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('VNL2_oneBand_repr.nc'),
                                           'VNL2_oneBand_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

    def test_africa_input(self, mock_download, mock_stage, mock_datetime):
        """ Nominal (successful) reprojection of test/data/africa.nc, using
            geographic coordinates, bilinear interpolation and specifying the
            extent of the target area grid.

            Also ensure that the provenance of the output file includes a
            record of the operation performed via the `history` and
            `history_json` global attributes.

        """
        input_file_path = 'test/data/africa.nc'

        mock_datetime.utcnow = Mock(return_value=datetime(2021, 5, 12, 19, 3, 4))
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': input_file_path,
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

        mock_download.assert_called_once_with(input_file_path,
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('africa_repr.nc'),
                                           'africa_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

        output_path = mock_stage.call_args[0][0]
        history, history_uppercase, history_json = self.get_provenance(output_path)

        expected_history = ('2021-05-12T19:03:04+00:00 sds/swot-reproject '
                            '0.9.0 {"crs": "EPSG:4326", "interpolation": '
                            '"bilinear", "x_min": -20, "x_max": 60, "y_min": '
                            '10, "y_max": 35}')

        expected_history_json = [{
            '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
            'date_time': '2021-05-12T19:03:04+00:00',
            'program': 'sds/swot-reproject',
            'version': '0.9.0',
            'parameters': {'crs': 'EPSG:4326',
                           'input_file': input_file_path,
                           'interpolation': 'bilinear',
                           'x_min': -20,
                           'x_max': 60,
                           'y_min': 10,
                           'y_max': 35},
            'derived_from': input_file_path,
            'program_ref': 'https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST',
        }]

        self.assertEqual(history, expected_history)
        self.assertIsNone(history_uppercase)
        self.assertListEqual(json.loads(history_json), expected_history_json)

    def test_africa_input_with_history_and_history_json(self, mock_download,
                                                        mock_stage, mock_datetime):
        """ Ensure that an input file with existing `history` and
            `history_json` global attributes include these metadata in the
            output `history` and `history_json` global attributes.

            This test will use a temporary copy of the `africa.nc` granule,
            and update the global attributes to include values for `history`
            and `history_json`. This updated file will then be used as input
            to the service.

        """
        input_file_path = f'{self.tmp_dir}/africa.nc'
        old_history = '2000-01-02T03:04:05.123456+00.00 Swathinator v0.0.1'
        old_history_json = json.dumps([{
            '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
            'date_time': '2021-05-12T19:03:04+00:00',
            'program': 'Swathinator',
            'version': '0.0.1',
            'parameters': {'input_file': 'africa.nc'},
            'derived_from': 'africa.nc',
            'program_ref': 'Swathinator Reference'
        }])

        with Dataset(input_file_path, 'a') as input_dataset:
            input_dataset.setncattr('history', old_history)
            input_dataset.setncattr('history_json', old_history_json)

        mock_datetime.utcnow = Mock(return_value=datetime(2021, 5, 12, 19, 3, 4))
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': input_file_path,
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

        mock_download.assert_called_once_with(input_file_path,
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('africa_repr.nc'),
                                           'africa_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

        output_path = mock_stage.call_args[0][0]
        history, history_uppercase, history_json = self.get_provenance(output_path)

        expected_history = (
            '2000-01-02T03:04:05.123456+00.00 Swathinator v0.0.1\n'
            '2021-05-12T19:03:04+00:00 sds/swot-reproject 0.9.0 '
            '{"crs": "EPSG:4326", "interpolation": "bilinear", "x_min": -20, '
            '"x_max": 60, "y_min": 10, "y_max": 35}'
        )

        expected_history_json = [{
            '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
            'date_time': '2021-05-12T19:03:04+00:00',
            'program': 'Swathinator',
            'version': '0.0.1',
            'parameters': {'input_file': 'africa.nc'},
            'derived_from': 'africa.nc',
            'program_ref': 'Swathinator Reference'
        }, {
            '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
            'date_time': '2021-05-12T19:03:04+00:00',
            'program': 'sds/swot-reproject',
            'version': '0.9.0',
            'parameters': {'crs': 'EPSG:4326',
                           'input_file': input_file_path,
                           'interpolation': 'bilinear',
                           'x_min': -20,
                           'x_max': 60,
                           'y_min': 10,
                           'y_max': 35},
            'derived_from': input_file_path,
            'cf_history': ['2000-01-02T03:04:05.123456+00.00 Swathinator v0.0.1'],
            'program_ref': 'https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST'
        }]

        self.assertEqual(history, expected_history)
        self.assertIsNone(history_uppercase)
        self.assertListEqual(json.loads(history_json), expected_history_json)

    def test_africa_input_with_history_uppercase(self, mock_download,
                                                 mock_stage, mock_datetime):
        """ Ensure that an input file with an existing `History` global
            attribute can be successfully projected, and that this existing
            metadata is included in the output `History` and `history_json`
            global attributes.

            This test will use a temporary copy of the `africa.nc` granule,
            and update the global attributes to include values for `History`.
            This updated file will then be used as input to the service.

        """
        input_file_path = 'test/data/africa_History.nc'
        input_file_path = f'{self.tmp_dir}/africa.nc'
        old_history = '2000-01-02T03:04:05.123456+00.00 Swathinator v0.0.1'

        with Dataset(input_file_path, 'a') as input_dataset:
            input_dataset.setncattr('History', old_history)

        mock_datetime.utcnow = Mock(return_value=datetime(2021, 5, 12, 19, 3, 4))
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': input_file_path,
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

        mock_download.assert_called_once_with(input_file_path,
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('africa_repr.nc'),
                                           'africa_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

        output_path = mock_stage.call_args[0][0]
        history, history_uppercase, history_json = self.get_provenance(output_path)

        expected_history_uppercase = (
            '2000-01-02T03:04:05.123456+00.00 Swathinator v0.0.1\n'
            '2021-05-12T19:03:04+00:00 sds/swot-reproject 0.9.0 '
            '{"crs": "EPSG:4326", "interpolation": "bilinear", "x_min": -20, '
            '"x_max": 60, "y_min": 10, "y_max": 35}'
        )

        expected_history_json = [{
            '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
            'date_time': '2021-05-12T19:03:04+00:00',
            'program': 'sds/swot-reproject',
            'version': '0.9.0',
            'parameters': {'crs': 'EPSG:4326',
                           'input_file': input_file_path,
                           'interpolation': 'bilinear',
                           'x_min': -20,
                           'x_max': 60,
                           'y_min': 10,
                           'y_max': 35},
            'derived_from': input_file_path,
            'program_ref': 'https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST',
            'cf_history': ['2000-01-02T03:04:05.123456+00.00 Swathinator v0.0.1']
        }]

        self.assertIsNone(history)
        self.assertEqual(history_uppercase, expected_history_uppercase)
        self.assertListEqual(json.loads(history_json), expected_history_json)

    def test_single_band_input_default_crs(self, mock_download, mock_stage,
                                           mock_datetime):
        """ Nominal (successful) reprojection of a single band input. This
            will default to using a geographic coordinate system, and use the
            Elliptically Weighted Average (EWA) interpolation method to derive
            the reprojected variables.

        """
        input_file_path = 'test/data/VNL2_oneBand.nc'

        mock_datetime.utcnow = Mock(return_value=datetime(2021, 5, 12, 19, 3, 4))
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': input_file_path,
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

        mock_download.assert_called_once_with(input_file_path,
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('VNL2_oneBand_repr.nc'),
                                           'VNL2_oneBand_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

        output_path = mock_stage.call_args[0][0]
        history, history_uppercase, history_json = self.get_provenance(output_path)

        expected_history = (
            'Tue Nov 12 15:31:14 2019: ncks -v sea_surface_temperature '
            'VNL2PSST_20190109000457-NAVO-L2P_GHRSST-SST1m-VIIRS'
            '_NPP-v02.0-fv03.0.nc VNL2_oneBand.nc\n'
            'Created with VIIRSseatemp on  2019/01/09 at 00:57:15 UT\n'
            '2021-05-12T19:03:04+00:00 sds/swot-reproject '
            '0.9.0 {"crs": "+proj=longlat +ellps=WGS84", '
            '"interpolation": "ewa", "x_min": -160, '
            '"x_max": -159, "y_min": 24, "y_max": 25}'
        )

        expected_history_json = [{
            '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
            'date_time': '2021-05-12T19:03:04+00:00',
            'program': 'sds/swot-reproject',
            'version': '0.9.0',
            'parameters': {'crs': '+proj=longlat +ellps=WGS84',
                           'input_file': input_file_path,
                           'interpolation': 'ewa',
                           'x_min': -160,
                           'x_max': -159,
                           'y_min': 24,
                           'y_max': 25},
            'derived_from': input_file_path,
            'program_ref': 'https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST',
            'cf_history': [('Tue Nov 12 15:31:14 2019: ncks -v sea_surface_temperature '
                            'VNL2PSST_20190109000457-NAVO-L2P_GHRSST-SST1m-VIIRS'
                            '_NPP-v02.0-fv03.0.nc VNL2_oneBand.nc'),
                            'Created with VIIRSseatemp on  2019/01/09 at 00:57:15 UT']
        }]

        self.assertEqual(history, expected_history)
        self.assertIsNone(history_uppercase)
        self.assertListEqual(json.loads(history_json), expected_history_json)

    def test_single_band_input_reprojected_metres(self, mock_download,
                                                  mock_stage, mock_datetime):
        """ Nominal (successful) reprojection of the single band input file,
            specifying the UTM Zone 3N (EPSG:32603) target projection and the
            Elliptically Weighted Average, Nearest Neighbour (EWA-NN)
            interpolation algorithm to derive the reprojected variables.

            Note: This choice of target CRS is due to the location of the
            input data being near the Hawaiian islands.

        """
        input_file_path = 'test/data/VNL2_oneBand.nc'
        mock_datetime.utcnow = Mock(return_value=datetime(2021, 5, 12, 19, 3, 4))
        test_data = Message({
            'accessToken': self.access_token,
            'callback': self.callback,
            'stagingLocation': self.staging_location,
            'sources': [{
                'granules': [{
                    'url': input_file_path,
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

        mock_download.assert_called_once_with(input_file_path,
                                              ANY,
                                              logger=ANY,
                                              access_token=self.access_token,
                                              cfg=ANY)
        mock_stage.assert_called_once_with(StringContains('VNL2_oneBand_repr.nc'),
                                           'VNL2_oneBand_regridded.nc',
                                           self.mime_type,
                                           location=self.staging_location,
                                           logger=ANY)

        output_path = mock_stage.call_args[0][0]
        history, history_uppercase, history_json = self.get_provenance(output_path)

        expected_history = (
            'Tue Nov 12 15:31:14 2019: ncks -v sea_surface_temperature '
            'VNL2PSST_20190109000457-NAVO-L2P_GHRSST-SST1m-VIIRS'
            '_NPP-v02.0-fv03.0.nc VNL2_oneBand.nc\n'
            'Created with VIIRSseatemp on  2019/01/09 at 00:57:15 UT\n'
            '2021-05-12T19:03:04+00:00 sds/swot-reproject 0.9.0 '
            '{"crs": "EPSG:32603", "interpolation": "ewa-nn", "x_min": 0, '
            '"x_max": 1500000, "y_min": 2500000, "y_max": 3300000}'
        )

        expected_history_json = [{
            '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
            'date_time': '2021-05-12T19:03:04+00:00',
            'program': 'sds/swot-reproject',
            'version': '0.9.0',
            'parameters': {'crs': 'EPSG:32603',
                           'input_file': input_file_path,
                           'interpolation': 'ewa-nn',
                           'x_min': 0,
                           'x_max': 1500000,
                           'y_min': 2500000,
                           'y_max': 3300000},
            'derived_from': input_file_path,
            'program_ref': 'https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST',
            'cf_history': [('Tue Nov 12 15:31:14 2019: ncks -v sea_surface_temperature '
                            'VNL2PSST_20190109000457-NAVO-L2P_GHRSST-SST1m-VIIRS'
                            '_NPP-v02.0-fv03.0.nc VNL2_oneBand.nc'),
                            'Created with VIIRSseatemp on  2019/01/09 at 00:57:15 UT']
        }]

        self.assertEqual(history, expected_history)
        self.assertIsNone(history_uppercase)
        self.assertListEqual(json.loads(history_json), expected_history_json)
