import numpy as np
import xarray

from PyMods.utilities import (create_coordinates_key, get_variable_values,
                              get_coordinate_variable,
                              get_variable_group_and_name)
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

        with self.subTest('Non existent coordinate variable returns None'):
            absent_coordinates_tuple = ['latitude']
            coordinates = get_coordinate_variable(dataset,
                                                  absent_coordinates_tuple,
                                                  absent_coordinates_tuple[0])

    def test_get_variable_group_and_name(self):
        """ Ensure a full variable name, containing the group is correctly
        split into the group and the name.

        """
        test_args = [['no_group', '', 'no_group'],
                     ['group_name/variable', 'group_name', 'variable'],
                     ['/nested/group/other_variable', '/nested/group', 'other_variable']]

        for variable_string, expected_group, expected_name in test_args:
            with self.subTest(variable_string):
                group, name = get_variable_group_and_name(variable_string)
                self.assertEqual(expected_group, group)
                self.assertEqual(expected_name, name)
