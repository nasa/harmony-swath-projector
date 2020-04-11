import numpy as np
import xarray

from PyMods.utilities import (create_coordinates_key, get_variable_values,
                              get_coordinate_variable, get_variables,
                              get_variable_name, is_coordinate_variable)
from test.test_utils import TestBase


class TestUtilities(TestBase):

    def test_create_coordinates_key(self):
        """ When given a string, ensure a list is returned that is split based
        on spaces, commas and space, commas.

        """
        test_args = [['spaces', 'lon lat'],
                     ['multiple spaces', 'lon    lat'],
                     ['comma', 'lon,lat'],
                     ['comma-space', 'lon, lat'],
                     ['comma-multiple-space', 'lon,    lat']]

        expected_output = ('lon', 'lat')

        for description, coordinates in test_args:
            with self.subTest(description):
                self.assertEqual(create_coordinates_key(coordinates),
                                 expected_output)

    def test_get_variable_values(self):
        """ Ensure values for a variable are retrieved, respecting the absence
            or presence of a time variable in the dataset.

        """

        with self.subTest('3-D dataset, with time'):
            dataset_with_time = xarray.open_dataset('test/data/africa.nc',
                                                    decode_cf=False)
            red_var = dataset_with_time.variables.get('red_var')
            self.assertEqual(len(red_var.shape), 3)

            red_var_values = get_variable_values(dataset_with_time, red_var)
            self.assertTrue(isinstance(red_var_values, np.ndarray))
            self.assertEqual(len(red_var_values.shape), 2)
            self.assertEqual(red_var_values.shape, red_var.shape[-2:])

            dataset_with_time.close()

    def test_get_coordinate_variables(self):
        """ Ensure the longitude or latitude coordinate variable, is retrieved
        when requested.

        """
        dataset = xarray.open_dataset('test/data/africa.nc', decode_cf=False)
        coordinates_tuple = ['lat', 'lon']

        for coordinate in coordinates_tuple:
            with self.subTest(coordinate):
                coordinates = get_coordinate_variable(dataset,
                                                      coordinates_tuple,
                                                      coordinate)

                self.assertTrue(isinstance(coordinates,
                                           xarray.core.variable.Variable))

        # Request a non-existent variable
        with self.subTest('Non existent coordinate variable returns None'):
            absent_coordinates_tuple = ['latitude']
            coordinates = get_coordinate_variable(dataset,
                                                  absent_coordinates_tuple,
                                                  absent_coordinates_tuple[0])

    def test_get_variables(self):
        """ Extract a full list of variables from a typical gdalinfo output
            string.

        """
        gdalinfo_string = (
            'Driver: netCDF/Network Common Data Format\n'
            'Files: test/data/africa.nc\n'
            'Size is 512, 512\n'
            'Metadata:\n'
            '  NC_GLOBAL#Conventions=CF-1.6\n'
            '  NC_GLOBAL#id=harmony_test_000_00_000_africa\n'
            '  NC_GLOBAL#naming_authority=gov.nasa.earthdata.harmony\n'
            '  NC_GLOBAL#product_version=1\n'
            '  NC_GLOBAL#summary=Harmony test dataset with swath-like values\n'
            '  NC_GLOBAL#title=Harmony Test L2\n'
            '  NC_GLOBAL#uuid=50b3dec2-845b-5a27-8ef3-7040ce0618aa\n'
            'Subdatasets:\n'
            '  SUBDATASET_1_NAME=NETCDF:"test/data/africa.nc":lat\n'
            '  SUBDATASET_1_DESC=[501x501] latitude (32-bit floating-point)\n'
            '  SUBDATASET_2_NAME=NETCDF:"test/data/africa.nc":lon\n'
            '  SUBDATASET_2_DESC=[501x501] longitude (32-bit floating-point)\n'
            '  SUBDATASET_3_NAME=NETCDF:"test/data/africa.nc":red_var\n'
            '  SUBDATASET_3_DESC=[1x501x501] red_var (8-bit unsigned integer)\n'
            '  SUBDATASET_4_NAME=NETCDF:"test/data/africa.nc":green_var\n'
            '  SUBDATASET_4_DESC=[1x501x501] green_var (8-bit unsigned integer)\n'
            '  SUBDATASET_5_NAME=NETCDF:"test/data/africa.nc":blue_var\n'
            '  SUBDATASET_5_DESC=[1x501x501] blue_var (8-bit unsigned integer)\n'
            '  SUBDATASET_6_NAME=NETCDF:"test/data/africa.nc":alpha_var\n'
            '  SUBDATASET_6_DESC=[1x501x501] alpha_var (8-bit unsigned integer)\n'
            'Corner Coordinates:\n'
            'Upper Left  (    0.0,    0.0)\n'
            'Lower Left  (    0.0,  512.0)\n'
            'Upper Right (  512.0,    0.0)\n'
            'Lower Right (  512.0,  512.0)\n'
            'Center      (  256.0,  256.0)\n'
        )

        expected_variables = ['NETCDF:"test/data/africa.nc":lat',
                              'NETCDF:"test/data/africa.nc":lon',
                              'NETCDF:"test/data/africa.nc":red_var',
                              'NETCDF:"test/data/africa.nc":green_var',
                              'NETCDF:"test/data/africa.nc":blue_var',
                              'NETCDF:"test/data/africa.nc":alpha_var']

        self.assertEqual(get_variables(gdalinfo_string), expected_variables)

    def test_get_variable_name(self):
        """ Ensure the last part of an input string, spit by colons is
            returned.

        """
        test_args = [['no_colon', 'no_colon'],
                     ['single_colon:variable', 'variable'],
                     ['multi:colon:other_variable', 'other_variable']]

        for variable_string, result in test_args:
            with self.subTest(variable_string):
                self.assertEqual(get_variable_name(variable_string), result)

    def test_is_coordiante_variable(self):
        """ Ensure coordinate variables are correctly identified."""

        test_args = [['lat', True], ['lon', True], ['latitude', True],
                     ['longitude', True], ['Something else', False]]

        for variable_name, result in test_args:
            with self.subTest(variable_name):
                self.assertEqual(is_coordinate_variable(variable_name), result)
