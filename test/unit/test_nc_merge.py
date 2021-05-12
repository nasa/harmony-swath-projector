from unittest.mock import patch
import logging
import os

from netCDF4 import Dataset
import numpy as np

from pymods.exceptions import MissingReprojectedDataError
from pymods.nc_info import NCInfo
from pymods.nc_merge import (check_coor_valid, create_output,
                             get_fill_value_from_attributes,
                             get_science_variable_attributes,
                             get_science_variable_dimensions, read_attrs)
from test.test_utils import TestBase


class TestNCMerge(TestBase):

    @classmethod
    def setUpClass(cls):
        cls.logger = logging.getLogger('nc_merge test')
        cls.properties = {'input_file':'test/data/VNL2_test_data.nc'}
        cls.tmp_dir = 'test/data/test_tmp/'
        cls.output_file = 'test/data/VNL2_test_data_repr.nc'
        cls.science_variables = {'/brightness_temperature_4um',
                                 '/satellite_zenith_angle',
                                 '/sea_surface_temperature', '/wind_speed'}
        cls.metadata_variables = set()
        create_output(cls.properties, cls.output_file, cls.tmp_dir,
                      cls.science_variables, cls.metadata_variables,
                      cls.logger)


    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.output_file):
            os.remove(cls.output_file)

    def test_output_has_all_variables(self):
        """ Output file has all expected variables from the input file. """
        output_info = NCInfo(self.output_file)
        output_science_variables = output_info.get_science_variables()
        self.assertSetEqual(output_science_variables, self.science_variables)

        # Output also has a CRS grid_mapping variable, and three dimensions:
        self.assertEqual(output_info.ancillary_data, {'/latitude_longitude'})
        self.assertEqual(output_info.dims, {'/lat', '/lon', '/time'})

    def test_same_dimensions(self):
        """ Corresponding variables in input and output should have the same
            number of dimensions.

        """
        test_dataset = 'sea_surface_temperature'
        in_dataset = Dataset(self.properties['input_file'])
        out_dataset = Dataset(self.output_file)
        self.assertEqual(len(in_dataset[test_dataset].dimensions),
                         len(out_dataset[test_dataset].dimensions))

    def test_output_global_attributes(self):
        """ The root group of the output files should have the same global attributes.
            Both the history_json and history attributes are in the output file
        """
        in_dataset = Dataset(self.properties['input_file'])
        out_dataset = Dataset(self.output_file)
        input_attrs = read_attrs(in_dataset)
        output_attrs = read_attrs(out_dataset)
        for input_key, input_value in input_attrs.items():
            self.assertIn(input_key, output_attrs.keys())
            if input_key != "history":
                self.assertEqual(input_value, output_attrs[input_key])

        self.assertIn('history', output_attrs.keys())
        #self.assertAlmostEquals(output_attrs['history'], 'Mon Dec  9 11:22:11 2019: ncks -v sea_surface_temperature,satellite_zenith_angle,brightness_temperature_4um,wind_speed /Users/yzhang29/Desktop/NCOTest/VNL2PSST_20190109000457-NAVO-L2P_GHRSST-SST1m-VIIRS_NPP-v02.0-fv03.0.nc /Users/yzhang29/Desktop/NCOTest/VNL2_test_data.nc/nCreated with VIIRSseatemp on  2019/01/09 at 00:57:15 UT/n2021-05-12T19:03:04.419341+00:00 sds/swot-reproject 0.9.0 test/data/VNL2_test_data.nc')
        self.assertIn('history_json', output_attrs.keys())
        #self.assertAlmostEquals(output_attrs['history_json'], '{"$schema": "https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-0.1.0.json", "time": "2021-05-12T19:03:04.419341+00:00", "program": "sds/swot-reproject", "version": "0.9.0", "parameters": {"input_file": "test/data/VNL2_test_data.nc"}, "derived_from": "test/data/VNL2_test_data.nc", "cf_history": ["Mon Dec  9 11:22:11 2019: ncks -v sea_surface_temperature,satellite_zenith_angle,brightness_temperature_4um,wind_speed /Users/yzhang29/Desktop/NCOTest/VNL2PSST_20190109000457-NAVO-L2P_GHRSST-SST1m-VIIRS_NPP-v02.0-fv03.0.nc /Users/yzhang29/Desktop/NCOTest/VNL2_test_data.nc", "Created with VIIRSseatemp on  2019/01/09 at 00:57:15 UT", "2021-05-12T19:03:04.419341+00:00 sds/swot-reproject 0.9.0 test/data/VNL2_test_data.nc"], "program_ref": "https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST"}')


    def test_same_num_of_dataset_attributes(self):
        """ Variables in input should have the same number of attributes. """
        test_variable = 'sea_surface_temperature'
        in_dataset = Dataset(self.properties['input_file'])
        out_dataset = Dataset(self.output_file)
        inf_data = in_dataset[test_variable]
        out_data = out_dataset[test_variable]
        input_attrs = read_attrs(inf_data)
        output_attrs = read_attrs(out_data)
        self.assertEqual(len(input_attrs), len(output_attrs))

    def test_same_data_type(self):
        """ Variables in input and output should have same data type. """
        test_variable = 'sea_surface_temperature'
        in_dataset = Dataset(self.properties['input_file'])
        out_dataset = Dataset(self.output_file)
        input_data_type = in_dataset[test_variable].datatype
        output_data_type = out_dataset[test_variable].datatype
        self.assertEqual(input_data_type, output_data_type, 'Should be equal')

    def test_missing_file_raises_error(self):
        """ If a science variable should be included in the output, but there
            is no associated output file, an exception should be raised.

        """
        test_variables = {'missing_variable'}
        temporary_output_file = 'test/data/unit_test.nc4'

        with self.assertRaises(MissingReprojectedDataError):
            create_output(self.properties, temporary_output_file, self.tmp_dir,
                          test_variables, self.metadata_variables, self.logger)

        if os.path.exists(temporary_output_file):
            os.remove(temporary_output_file)

    def test_get_fill_value_from_attributes(self):
        """ If a variable has a fill value it should be popped from the
            dictionary and returned. Otherwise, the default value of `None`
            should be returned.

        """
        with self.subTest('_FillValue present in attributes'):
            fill_value = 123
            attributes = {'_FillValue': fill_value}
            self.assertEqual(get_fill_value_from_attributes(attributes),
                             fill_value)
            self.assertNotIn('_FillValue', attributes)

        with self.subTest('_FillValue absent, returns None'):
            self.assertEqual(get_fill_value_from_attributes({}), None)

    def test_check_coord_valid(self):
        """ If some of the listed coordinates are not in the single band
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
            self.assertTrue(check_coor_valid({}, '/brightness_temperature_4um',
                                             input_dataset, single_band_dataset))

        with self.subTest('Reprojected data missing coordinates returns False'):
            attributes = {'coordinates': 'random, string, values'}
            self.assertFalse(check_coor_valid(attributes,
                                              '/brightness_temperature_4um',
                                              input_dataset,
                                              single_band_dataset))

        with self.subTest('Reprojected data with different shape returns False'):
            attributes = {'coordinates': 'lat lon'}
            self.assertFalse(check_coor_valid(attributes,
                                              '/brightness_temperature_4um',
                                              input_dataset,
                                              single_band_dataset))

        with self.subTest('Reprojected data with preserved coordinates returns True'):
            # To ensure a match, this uses two different reprojected output
            # files, as these are guaranteed to match coordinate shapes.
            second_dataset = Dataset(f'{self.tmp_dir}wind_speed.nc')
            attributes = {'coordinates': 'lat lon'}

            self.assertTrue(check_coor_valid(attributes, '/wind_speed',
                                             second_dataset,
                                             single_band_dataset))

    def test_get_science_variable_dimensions(self):
        """ Ensure that the retrieved dimensions match those in the single band
            dataset. If the input dataset includes a time dimension, that
            should be included in the returned tuple.

        """
        variable_name = 'sea_surface_temperature'
        single_band_dataset = Dataset(f'{self.tmp_dir}{variable_name}.nc')
        input_dataset = Dataset(self.properties['input_file'])

        with self.subTest('Input dataset has time dimension.'):
            dimensions = get_science_variable_dimensions(input_dataset,
                                                         single_band_dataset,
                                                         variable_name)
            self.assertTupleEqual(dimensions, ('time', 'lat', 'lon'))

        with self.subTest('Input dataset has no time dimension.'):
            # Using the single_band_dataset as input ensure no time dimension
            dimensions = get_science_variable_dimensions(single_band_dataset,
                                                         single_band_dataset,
                                                         'lat')
            self.assertTupleEqual(dimensions, ('lat',))

    @patch('pymods.nc_merge.check_coor_valid')
    def test_get_science_variable_attributes(self, mock_check_coord_valid):
        """ The original input metadata should be mostly present. The
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
            attributes = get_science_variable_attributes(input_dataset,
                                                         single_band_dataset,
                                                         variable_name)

            input_attributes = input_dataset[variable_name].__dict__
            single_band_attributes = single_band_dataset[variable_name].__dict__

            # This will include the `coordinates` attribute from the input.
            for attribute_name, attribute_value in input_attributes.items():
                self.assertIn(attribute_name, attributes)
                self.assertEqual(attributes[attribute_name], attribute_value)

            self.assertIn('grid_mapping', attributes)
            self.assertEqual(attributes['grid_mapping'],
                             single_band_attributes['grid_mapping'])

        with self.subTest('Coordinates are no longer valid.'):
            mock_check_coord_valid.return_value = False
            attributes = get_science_variable_attributes(input_dataset,
                                                         single_band_dataset,
                                                         variable_name)

            input_attributes = input_dataset[variable_name].__dict__
            single_band_attributes = single_band_dataset[variable_name].__dict__

            self.assertNotIn('coordinates', attributes)

            for attribute_name, attribute_value in input_attributes.items():
                if attribute_name != 'coordinates':
                    self.assertIn(attribute_name, attributes)
                    self.assertEqual(attributes[attribute_name],
                                     attribute_value)

            self.assertIn('grid_mapping', attributes)
            self.assertEqual(attributes['grid_mapping'],
                             single_band_attributes['grid_mapping'])
