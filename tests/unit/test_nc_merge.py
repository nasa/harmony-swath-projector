import json
import logging
import os
from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock, patch

from netCDF4 import Dataset
from varinfo import VarInfoFromNetCDF4

from swath_projector.exceptions import MissingReprojectedDataError
from swath_projector.nc_merge import (
    check_coor_valid,
    create_history_record,
    create_output,
    get_fill_value_from_attributes,
    get_science_variable_attributes,
    read_attrs,
)
from swath_projector.reproject import CF_CONFIG_FILE


class TestNCMerge(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.logger = logging.getLogger('nc_merge test')
        cls.properties = {
            'input_file': 'tests/data/VNL2_test_data.nc',
            'granule_url': 'tests/data/VNL2_test_data.nc',
            'crs': 'EPSG:4326',
            'interpolation': 'bilinear',
        }

        cls.tmp_dir = 'tests/data/test_tmp/'
        cls.output_file = 'tests/data/VNL2_test_data_repr.nc'
        cls.science_variables = {
            '/brightness_temperature_4um',
            '/satellite_zenith_angle',
            '/sea_surface_temperature',
            '/wind_speed',
        }

        cls.metadata_variables = set()
        cls.var_info = VarInfoFromNetCDF4(
            cls.properties['input_file'],
            short_name='VIIRS_NPP-NAVO-L2P-v3.0',
            config_file=CF_CONFIG_FILE,
        )
        create_output(
            cls.properties,
            cls.output_file,
            cls.tmp_dir,
            cls.science_variables,
            cls.metadata_variables,
            cls.logger,
            cls.var_info,
        )

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.output_file):
            os.remove(cls.output_file)

    def test_output_has_all_variables(self):
        """Output file has all expected variables from the input file."""
        with Dataset(self.output_file, 'r') as output_dataset:
            # Output has all projected science variables:
            for expected_variable in self.science_variables:
                self.assertIn(expected_variable.lstrip('/'), output_dataset.variables)

            # Output also has a CRS grid_mapping variable, and three dimensions:
            self.assertIn('latitude_longitude', output_dataset.variables)
            for expected_dimension in {'lat', 'lon', 'time'}:
                self.assertIn(expected_dimension, output_dataset.variables)

    def test_same_dimensions(self):
        """Corresponding variables in input and output should have the same
        number of dimensions.

        """
        test_dataset = 'sea_surface_temperature'
        in_dataset = Dataset(self.properties['input_file'])
        out_dataset = Dataset(self.output_file)
        self.assertEqual(
            len(in_dataset[test_dataset].dimensions),
            len(out_dataset[test_dataset].dimensions),
        )

    @patch('swath_projector.nc_merge.datetime')
    def test_output_global_attributes(self, mock_datetime):
        """The root group of the output files should contain the global
        attributes of the input file, with the addition of `history` (if
        not originally present) and `history_json`.

        """
        mock_datetime.utcnow = Mock(return_value=datetime(2021, 5, 12, 19, 3, 4))

        create_output(
            self.properties,
            self.output_file,
            self.tmp_dir,
            self.science_variables,
            self.metadata_variables,
            self.logger,
            self.var_info,
        )

        with Dataset(self.properties['input_file']) as in_dataset:
            input_attrs = read_attrs(in_dataset)

        with Dataset(self.output_file) as out_dataset:
            output_attrs = read_attrs(out_dataset)

        for input_key, input_value in input_attrs.items():
            self.assertIn(input_key, output_attrs.keys())
            if input_key != 'history':
                self.assertEqual(input_value, output_attrs[input_key])

        expected_history = (
            'Mon Dec  9 11:22:11 2019: ncks -v '
            'sea_surface_temperature,satellite_zenith_angle,'
            'brightness_temperature_4um,wind_speed '
            '/Users/yzhang29/Desktop/NCOTest/'
            'VNL2PSST_20190109000457-NAVO-L2P_GHRSST-SST1m-VIIRS_NPP-v02.0-fv03.0.nc '
            '/Users/yzhang29/Desktop/NCOTest/VNL2_test_data.nc\n'
            'Created with VIIRSseatemp on  2019/01/09 at 00:57:15 UT\n'
            '2021-05-12T19:03:04+00:00 sds/harmony-swath-projector 0.9.0 '
            '{"crs": "EPSG:4326", "interpolation": "bilinear"}'
        )

        self.assertIn('history', output_attrs.keys())
        self.assertEqual(output_attrs['history'], expected_history)
        self.assertNotIn('History', output_attrs.keys())

        expected_history_json = [
            {
                '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
                'date_time': '2021-05-12T19:03:04+00:00',
                'program': 'sds/harmony-swath-projector',
                'version': '0.9.0',
                'parameters': {
                    'input_file': 'tests/data/VNL2_test_data.nc',
                    'crs': 'EPSG:4326',
                    'interpolation': 'bilinear',
                },
                'derived_from': 'tests/data/VNL2_test_data.nc',
                'cf_history': [
                    (
                        'Mon Dec  9 11:22:11 2019: ncks -v '
                        'sea_surface_temperature,satellite_zenith_angle,'
                        'brightness_temperature_4um,wind_speed '
                        '/Users/yzhang29/Desktop/NCOTest/'
                        'VNL2PSST_20190109000457-NAVO-L2P_GHRSST-SST1m-VIIRS_NPP-v02.0-fv03.0.nc '
                        '/Users/yzhang29/Desktop/NCOTest/VNL2_test_data.nc'
                    ),
                    'Created with VIIRSseatemp on  2019/01/09 at 00:57:15 UT',
                ],
                'program_ref': 'https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST',
            }
        ]

        self.assertIn('history_json', output_attrs.keys())
        self.assertEqual(
            json.loads(output_attrs['history_json']), expected_history_json
        )

    def test_same_num_of_dataset_attributes(self):
        """Variables in input should have the same number of attributes."""
        test_variable = 'sea_surface_temperature'
        in_dataset = Dataset(self.properties['input_file'])
        out_dataset = Dataset(self.output_file)
        inf_data = in_dataset[test_variable]
        out_data = out_dataset[test_variable]
        input_attrs = read_attrs(inf_data)
        output_attrs = read_attrs(out_data)
        self.assertEqual(len(input_attrs), len(output_attrs))

    def test_same_data_type(self):
        """Variables in input and output should have same data type."""
        test_variable = 'sea_surface_temperature'
        in_dataset = Dataset(self.properties['input_file'])
        out_dataset = Dataset(self.output_file)
        input_data_type = in_dataset[test_variable].datatype
        output_data_type = out_dataset[test_variable].datatype
        self.assertEqual(input_data_type, output_data_type, 'Should be equal')

    def test_missing_file_raises_error(self):
        """If a science variable should be included in the output, but there
        is no associated output file, an exception should be raised.

        """
        test_variables = {'missing_variable'}
        temporary_output_file = 'tests/data/unit_test.nc4'

        with self.assertRaises(MissingReprojectedDataError):
            create_output(
                self.properties,
                temporary_output_file,
                self.tmp_dir,
                test_variables,
                self.metadata_variables,
                self.logger,
                self.var_info,
            )

        if os.path.exists(temporary_output_file):
            os.remove(temporary_output_file)

    def test_get_fill_value_from_attributes(self):
        """If a variable has a fill value it should be popped from the
        dictionary and returned. Otherwise, the default value of `None`
        should be returned.

        """
        with self.subTest('_FillValue present in attributes'):
            fill_value = 123
            attributes = {'_FillValue': fill_value}
            self.assertEqual(get_fill_value_from_attributes(attributes), fill_value)
            self.assertNotIn('_FillValue', attributes)

        with self.subTest('_FillValue absent, returns None'):
            self.assertEqual(get_fill_value_from_attributes({}), None)

    def test_check_coord_valid(self):
        """If some of the listed coordinates are not in the single band
        output, then the function should return `False`. If any of the
        any of the coordinate variables have different shapes in the input
        and the single band output, then the function should return
        `False`. Otherwise, the function should return `True`. Also check
        the case that no coordinates are listed.

        """
        test_dataset_name = 'sea_surface_temperature.nc'
        single_band_dataset = Dataset(f'{self.tmp_dir}{test_dataset_name}')
        input_dataset = Dataset(self.properties['input_file'])

        with self.subTest('No coordinate data returns True'):
            self.assertTrue(
                check_coor_valid(
                    self.var_info, '/lat', input_dataset, single_band_dataset
                )
            )

        with self.subTest('Reprojected data missing coordinates returns False'):
            self.assertFalse(
                check_coor_valid(
                    self.var_info,
                    '/brightness_temperature_4um',
                    input_dataset,
                    single_band_dataset,
                )
            )

        with self.subTest('Reprojected data with preserved coordinates returns True'):
            # To ensure a match, this uses two different reprojected output
            # files, as these are guaranteed to match coordinate shapes.
            second_dataset = Dataset(f'{self.tmp_dir}wind_speed.nc')

            self.assertTrue(
                check_coor_valid(
                    self.var_info, '/wind_speed', second_dataset, single_band_dataset
                )
            )

    @patch('swath_projector.nc_merge.check_coor_valid')
    def test_get_science_variable_attributes(self, mock_check_coord_valid):
        """The original input metadata should be mostly present. The
        `grid_mapping` metadata attribute should be added from the single
        band output. If the shapes of the variables listed as coordinates
        have changed in reprojection, then the `coordinates` metadata
        attribute not be present in the returned attributes.

        """
        variable_name = 'sea_surface_temperature'
        single_band_dataset = Dataset(f'{self.tmp_dir}{variable_name}.nc')
        input_dataset = Dataset(self.properties['input_file'])

        with self.subTest('Coordinates remain valid.'):
            mock_check_coord_valid.return_value = True
            attributes = get_science_variable_attributes(
                input_dataset, single_band_dataset, variable_name, self.var_info
            )

            input_attributes = input_dataset[variable_name].__dict__
            single_band_attributes = single_band_dataset[variable_name].__dict__

            # This will include the `coordinates` attribute from the input.
            for attribute_name, attribute_value in input_attributes.items():
                self.assertIn(attribute_name, attributes)
                self.assertEqual(attributes[attribute_name], attribute_value)

            self.assertIn('grid_mapping', attributes)
            self.assertEqual(
                attributes['grid_mapping'], single_band_attributes['grid_mapping']
            )

        with self.subTest('Coordinates are no longer valid.'):
            mock_check_coord_valid.return_value = False
            attributes = get_science_variable_attributes(
                input_dataset, single_band_dataset, variable_name, self.var_info
            )

            input_attributes = input_dataset[variable_name].__dict__
            single_band_attributes = single_band_dataset[variable_name].__dict__

            self.assertNotIn('coordinates', attributes)

            for attribute_name, attribute_value in input_attributes.items():
                if attribute_name != 'coordinates':
                    self.assertIn(attribute_name, attributes)
                    self.assertEqual(attributes[attribute_name], attribute_value)

            self.assertIn('grid_mapping', attributes)
            self.assertEqual(
                attributes['grid_mapping'], single_band_attributes['grid_mapping']
            )

    @patch('swath_projector.nc_merge.datetime')
    def test_create_history_record(self, mock_datetime):
        """Ensure a history record is correctly constructed, and only contains
        a `cf_history` attribute if there is valid a `history` (or
        `History`) attribute specified from the input.

        """
        mock_datetime.utcnow = Mock(return_value=datetime(2001, 2, 3, 4, 5, 6))
        granule_url = 'https://example.com/input.nc4'
        request_parameters = {
            'crs': '+proj=longlat',
            'input_file': granule_url,
            'interpolation': 'near',
        }

        with self.subTest('No specified history'):
            expected_output = {
                '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
                'date_time': '2001-02-03T04:05:06+00:00',
                'program': 'sds/harmony-swath-projector',
                'version': '0.9.0',
                'parameters': request_parameters,
                'derived_from': granule_url,
                'program_ref': 'https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST',
            }
            self.assertDictEqual(
                create_history_record(None, request_parameters), expected_output
            )

        string_history = '2000-12-31T00:00:00+00.00 Swathinator v0.0.1'
        list_history = [string_history]
        expected_output_with_history = {
            '$schema': 'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json',
            'date_time': '2001-02-03T04:05:06+00:00',
            'program': 'sds/harmony-swath-projector',
            'version': '0.9.0',
            'parameters': request_parameters,
            'derived_from': granule_url,
            'program_ref': 'https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST',
            'cf_history': list_history,
        }

        with self.subTest('String history specified in input file'):
            self.assertDictEqual(
                create_history_record(string_history, request_parameters),
                expected_output_with_history,
            )

        with self.subTest('List history specified in input file'):
            self.assertDictEqual(
                create_history_record(list_history, request_parameters),
                expected_output_with_history,
            )
