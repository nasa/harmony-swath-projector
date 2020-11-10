import os

import netCDF4

from pymods.exceptions import MissingReprojectedDataError
from pymods.nc_info import NCInfo
from pymods.nc_merge import (check_coor_valid, create_output, get_dataset_meta,
                             get_dimensions, get_fill_value_from_attributes,
                             read_attrs)
from test.test_utils import TestBase


class TestNCMerge(TestBase):

    @classmethod
    def setUpClass(cls):
        cls.input_file = 'test/data/VNL2_test_data.nc'
        cls.tmp_dir = 'test/data/test_tmp/'
        cls.output_file = 'test/data/VNL2_test_data_repr.nc'
        cls.science_variables = {'brightness_temperature_4um',
                                 'satellite_zenith_angle',
                                 'sea_surface_temperature', 'wind_speed'}
        cls.metadata_variables = set()
        create_output(cls.input_file, cls.output_file, cls.tmp_dir,
                      cls.science_variables, cls.metadata_variables)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.output_file):
            os.remove(cls.output_file)

    def test_output_has_all_variables(self):
        """ Output file has all expected variables from the input file. """
        output_info = NCInfo(self.output_file)
        output_science_variables = output_info.get_science_variables()
        self.assertSetEqual(output_science_variables, self.science_variables)

        # Output also has a CRS variable, and three dimensions:
        self.assertEqual(output_info.ancillary_data, {'latitude_longitude'})
        self.assertEqual(output_info.dims, {'lat', 'lon', 'time'})

    def test_same_dimensions(self):
        """ Corresponding variables in input and output should have the same
            number of dimensions.

        """
        test_dataset = 'sea_surface_temperature.nc'
        test_file = netCDF4.Dataset(f'{self.tmp_dir}{test_dataset}')
        in_dataset = netCDF4.Dataset(self.input_file)
        out_dataset = netCDF4.Dataset(self.output_file)
        input_dim = get_dimensions(test_file,
                                   os.path.splitext(test_dataset)[0],
                                   in_dataset)
        output_dim = get_dimensions(test_file,
                                    os.path.splitext(test_dataset)[0],
                                    out_dataset)

        self.assertEqual(len(input_dim), len(output_dim))

    def test_same_global_attributes(self):
        """ The root group of the input and output files should have same
            global attributes.

        """
        in_dataset = netCDF4.Dataset(self.input_file)
        out_dataset = netCDF4.Dataset(self.output_file)
        input_attrs = read_attrs(in_dataset)
        output_attrs = read_attrs(out_dataset)
        self.assertDictEqual(input_attrs, output_attrs)

    def test_same_num_of_dataset_attributes(self):
        """ Variables in input should have the same number of attributes. """
        test_variable = 'sea_surface_temperature'
        in_dataset = netCDF4.Dataset(self.input_file)
        out_dataset = netCDF4.Dataset(self.output_file)
        inf_data = in_dataset[test_variable]
        out_data = out_dataset[test_variable]
        input_attrs = read_attrs(inf_data)
        output_attrs = read_attrs(out_data)
        self.assertEqual(len(input_attrs), len(output_attrs))

    def test_same_data_type(self):
        """ Variables in input and output should have same data type. """
        test_variable = 'sea_surface_temperature'
        in_dataset = netCDF4.Dataset(self.input_file)
        out_dataset = netCDF4.Dataset(self.output_file)
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
            create_output(self.input_file, temporary_output_file, self.tmp_dir,
                          test_variables, self.metadata_variables)

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
        single_band_dataset = netCDF4.Dataset(f'{self.tmp_dir}'
                                              f'{test_dataset_name}')
        input_dataset = netCDF4.Dataset(self.input_file)

        with self.subTest('No coordinate data returns True'):
            self.assertTrue(check_coor_valid({}, input_dataset,
                                             single_band_dataset))

        with self.subTest('Reprojected data missing coordinates returns False'):
            attributes = {'coordinates': 'random, string, values'}
            self.assertFalse(check_coor_valid(attributes, input_dataset,
                                              single_band_dataset))

        with self.subTest('Reprojected data with different shape returns False'):
            attributes = {'coordinates': 'lat lon'}
            self.assertFalse(check_coor_valid(attributes, input_dataset,
                                              single_band_dataset))

        with self.subTest('Reprojected data with preserved coordinates returns True'):
            # To ensure a match, this uses two different reprojected output
            # files, as these are guaranteed to match coordinate shapes.
            second_dataset = netCDF4.Dataset(f'{self.tmp_dir}wind_speed.nc')
            attributes = {'coordinates': 'lat lon'}

            self.assertTrue(check_coor_valid(attributes, second_dataset,
                                             single_band_dataset))

    def test_get_dimensions(self):
        """ Check the input dataset takes priority, and that a 'time' dimension
            is correctly identified. Otherwise determine the dimensions from
            the single band dataset, or return an empty tuple.

        """
        test_dataset_name = 'sea_surface_temperature.nc'
        single_band_dataset = netCDF4.Dataset(f'{self.tmp_dir}'
                                              f'{test_dataset_name}')
        input_dataset = netCDF4.Dataset(self.input_file)

        with self.subTest('No input_dataset, single band is array'):
            self.assertTupleEqual(get_dimensions(single_band_dataset, 'Band1'),
                                  ('Band1',))

        with self.subTest('No input_dataset, single band is scalar'):
            self.assertTupleEqual(get_dimensions(single_band_dataset, 'crs'),
                                  ())

        with self.subTest('input_dataset has time dimension'):
            self.assertTupleEqual(get_dimensions(single_band_dataset, 'Band1',
                                                 input_dataset),
                                  ('time', 'lat', 'lon'))

        with self.subTest('input_dataset does not have time dimension'):
            self.assertTupleEqual(get_dimensions(single_band_dataset, 'Band1',
                                                 single_band_dataset),
                                  ('lat', 'lon'))

    def test_get_dataset_meta(self):
        """ Check the dimensions, datatype and attributes are correctly
            retrieved.

        """
        test_dataset_name = 'sea_surface_temperature'
        single_band_dataset = netCDF4.Dataset(f'{self.tmp_dir}'
                                              f'{test_dataset_name}.nc')
        input_dataset = netCDF4.Dataset(self.input_file)

        with self.subTest('Variable name in single band output'):
            metadata = get_dataset_meta(input_dataset, single_band_dataset,
                                        'Band1')

            self.assertTupleEqual(metadata[0], ('Band1',))
            self.assertEqual(metadata[1],
                             single_band_dataset['Band1'].datatype)
            self.assertDictEqual(metadata[2],
                                 single_band_dataset['Band1'].__dict__)

        with self.subTest('Variable name not in single band output'):
            metadata = get_dataset_meta(input_dataset, single_band_dataset,
                                        test_dataset_name)

            expected_attrs = input_dataset[test_dataset_name].__dict__.copy()
            del expected_attrs['coordinates']
            expected_attrs['grid_mapping'] = 'crs'

            self.assertTupleEqual(metadata[0], ('time', 'lat', 'lon'))
            self.assertEqual(metadata[1],
                             input_dataset[test_dataset_name].datatype)
            self.assertDictEqual(metadata[2], expected_attrs)
