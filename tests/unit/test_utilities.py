from unittest import TestCase
from unittest.mock import Mock

from netCDF4 import Dataset, Variable
from varinfo import VarInfoFromNetCDF4
import numpy as np

from swath_projector.exceptions import MissingCoordinatesError
from swath_projector.utilities import (
    construct_absolute_path,
    create_coordinates_key,
    get_variable_values,
    get_coordinate_variable,
    get_scale_and_offset,
    get_variable_file_path,
    get_variable_numeric_fill_value,
    make_array_two_dimensional,
    qualify_reference,
    variable_in_dataset
)


class TestUtilities(TestCase):

    def test_create_coordinates_key(self):
        """ Extract the coordinates from a `VariableFromNetCDF4` instance and
            return an alphabetically sorted tuple. The ordering prevents any
            shuffling due to earthdata-varinfo storing CF-Convention attribute
            references as a Python Set.

        """
        data = np.ones((2, 4))
        dimensions = ('lat', 'lon')
        expected_output = ('/lat', '/lon')

        test_args = [['comma-space', ['/lon, /lat']],
                     ['reverse order', ['/lat, /lon']]]

        for description, coordinates in test_args:
            with self.subTest(description):
                with Dataset('test.nc', 'w') as dataset:
                    dataset.createDimension('lat', size=2)
                    dataset.createDimension('lon', size=4)

                    nc4_variable = dataset.createVariable(
                        '/group/variable', data.dtype, dimensions=dimensions
                    )
                    dataset.createVariable('/lat', data.dtype,
                                           dimensions=dimensions)
                    dataset.createVariable('/lon', data.dtype,
                                           dimensions=dimensions)

                    nc4_variable.setncattr('coordinates', coordinates)

                varinfo = VarInfoFromNetCDF4('test.nc')
                varinfo_variable = varinfo.get_variable('/group/variable')
                self.assertEqual(create_coordinates_key(varinfo_variable),
                                 expected_output)

    def test_get_variable_values(self):
        """ Ensure values for a variable are retrieved, respecting the absence
            or presence of a time variable in the dataset.

        """

        with self.subTest('3-D variable, with time.'):
            with Dataset('tests/data/africa.nc') as dataset:
                red_var = dataset['red_var']
                self.assertEqual(len(red_var.shape), 3)

                red_var_values = get_variable_values(dataset, red_var, None)
                self.assertIsInstance(red_var_values, np.ndarray)
                self.assertEqual(len(red_var_values.shape), 2)
                self.assertEqual(red_var_values.shape, red_var.shape[-2:])

        with self.subTest('2-D variable, no time.'):
            with Dataset('tests/data/test_tmp/wind_speed.nc') as dataset:
                wind_speed = dataset['wind_speed']
                self.assertEqual(len(wind_speed.shape), 2)

                wind_speed_values = get_variable_values(dataset, wind_speed, None)
                self.assertIsInstance(wind_speed_values, np.ndarray)
                self.assertEqual(len(wind_speed_values.shape), 2)
                self.assertEqual(wind_speed_values.shape, wind_speed.shape)

        with self.subTest('Masked values are set to fill value.'):
            fill_value = 210
            input_data = np.array([[220, 210], [240, 234]])

            with Dataset('mock_data.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('y', size=2)
                dataset.createDimension('x', size=2)
                dataset.createVariable('data', np.uint8, dimensions=('y', 'x'),
                                       fill_value=fill_value)
                dataset['data'][:] = input_data

                # Ensure the raw variable data is masked in the expected cell.
                self.assertTrue(dataset['data'][:].mask[0, 1])

                returned_data = get_variable_values(dataset, dataset['data'],
                                                    fill_value)

                # Check the output is an array, not a masked array.
                self.assertIsInstance(returned_data, np.ndarray)
                # Check the output matches all the input data
                np.testing.assert_array_equal(input_data, returned_data)

        with self.subTest('2-D variable, time in dataset, but not variable'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('time', size=1)
                dataset.createDimension('lat', size=2)
                dataset.createDimension('lon', size=2)
                input_data = np.array([[1, 2], [3, 4]])
                variable = dataset.createVariable('data', input_data.dtype,
                                                  dimensions=('lat', 'lon'))
                variable[:] = input_data[:]

                returned_data = get_variable_values(dataset, variable, None)

                self.assertIsInstance(returned_data, np.ndarray)
                np.testing.assert_array_equal(input_data, returned_data)

    def test_get_coordinate_variables(self):
        """ Ensure the longitude or latitude coordinate variable, is retrieved
            when requested.

        """
        dataset = Dataset('tests/data/africa.nc')
        coordinates_tuple = ['lat', 'lon']

        for coordinate in coordinates_tuple:
            with self.subTest(coordinate):
                coordinates = get_coordinate_variable(dataset,
                                                      coordinates_tuple,
                                                      coordinate)

                self.assertIsInstance(coordinates, Variable)

        with self.subTest('Non existent coordinate variable "latitude" returns MissingCoordinatesError'):
            absent_coordinates_tuple = ['latitude']
            with self.assertRaises(MissingCoordinatesError):
                coordinates = get_coordinate_variable(
                    dataset,
                    absent_coordinates_tuple,
                    absent_coordinates_tuple[0]
                )

    def test_get_variable_numeric_fill_value(self):
        """ Ensure a fill value is retrieved from a variable that has a vaild
            numeric value, and is cast as either an integer or a float. If no
            fill value is present on the variable, or the fill value is non-
            numeric, the function should return None. This is because
            pyresample explicitly checks for float or int fill values in
            get_sample_from_neighbour_info.

        """
        variable = Mock(spec=Variable)

        test_args = [['np.float128', np.float128, 4.0, 4.0],
                     ['np.float16', np.float16, 4.0, 4.0],
                     ['np.float32', np.float32, 4.0, 4.0],
                     ['np.float64', np.float64, 4.0, 4.0],
                     ['np.float_', np.float_, 4.0, 4.0],
                     ['int', int, 5, 5],
                     ['np.int0', np.int0, 5, 5],
                     ['np.int16', np.int16, 5, 5],
                     ['np.int32', np.int32, 5, 5],
                     ['np.int64', np.int64, 5, 5],
                     ['np.int8', np.int8, 5, 5],
                     ['np.uint', np.uint, 5, 5],
                     ['np.uint0', np.uint0, 5, 5],
                     ['np.uint16', np.uint16, 5, 5],
                     ['np.uint32', np.uint32, 5, 5],
                     ['np.uint64', np.uint64, 5, 5],
                     ['np.uint8', np.uint8, 5, 5],
                     ['np.uintc', np.uintc, 5, 5],
                     ['np.uintp', np.uintp, 5, 5],
                     ['np.longlong', np.longlong, 5, 5],
                     ['float', float, 4.0, 4.0],
                     ['int', int, 5, 5],
                     ['str', str, '1235', None]]

        for description, caster, fill_value, expected_output in test_args:
            with self.subTest(description):
                variable.ncattrs.return_value = ['_FillValue']
                variable.getncattr.return_value = caster(fill_value)
                self.assertEqual(get_variable_numeric_fill_value(variable),
                                 expected_output)

        with self.subTest('Missing fill value attribute returns `None`.'):
            variable.ncattrs.return_value = ['other_attribute']
            self.assertEqual(get_variable_numeric_fill_value(variable), None)

        with self.subTest('Variable with fill value is scaled.'):
            raw_fill_value = 1
            add_offset = 210
            scale_factor = 2
            variable.ncattrs.return_value = ['add_offset', '_FillValue',
                                             'scale_factor']
            variable.getncattr.side_effect = [raw_fill_value, add_offset,
                                              scale_factor]

            self.assertEqual(get_variable_numeric_fill_value(variable), 212)

    def test_get_variable_file_path(self):
        """ Ensure that a file path is correctly constructed from a variable
            name. This should also handle a variable within a group, not just
            at the root level of the dataset.

        """
        temporary_directory = '/tmp_dir'
        file_extension = '.nc'

        test_args = [['Root variable', 'var_one', '/tmp_dir/var_one.nc'],
                     ['Nested variable', '/group/var_two',
                      '/tmp_dir/group_var_two.nc']]

        for description, variable_name, expected_path in test_args:
            with self.subTest(description):
                variable_path = get_variable_file_path(temporary_directory,
                                                       variable_name,
                                                       file_extension)
            self.assertEqual(variable_path, expected_path)

    def test_get_scale_and_offset(self):
        """ Ensure that the scaling attributes can be correctly returned from
            the input variable attributes, or an empty dictionary if both
            add_offset` and `scale_factor` are not present.

        """
        variable = Mock(spec=Variable)
        false_tests = [
            ['Neither attribute present.', {'other_key': 123}],
            ['Only scale_factor is present.', {'scale_factor': 0.01}],
            ['Only add_offset is present.', {'add_offset': 123.456}]
        ]

        for description, attributes in false_tests:
            variable.ncattrs.return_value = set(attributes.keys())
            with self.subTest(description):
                self.assertDictEqual(get_scale_and_offset(variable), {})

                variable.getncattr.assert_not_called()

        with self.subTest('Contains both required attributes'):
            attributes = {'add_offset': 123.456,
                          'scale_factor': 0.01,
                          'other_key': 'abc'}

            variable.ncattrs.return_value = set(attributes.keys())
            variable.getncattr.side_effect = [123.456, 0.01]
            self.assertDictEqual(get_scale_and_offset(variable),
                                 {'add_offset': 123.456, 'scale_factor': 0.01})

    def test_construct_absolute_path(self):
        """ Ensure that an absolute path can be constructed from a relative one
            and the supplied group path.

        """
        test_args = [
            ['Reference in group', 'variable', '/group', '/group/variable'],
            ['Reference in parent', '../variable', '/group', '/variable'],
            ['Reference in grandparent', '../../var', '/g1/g2', '/var'],
        ]

        for description, reference, group_path, abs_reference in test_args:
            with self.subTest(description):
                self.assertEqual(
                    construct_absolute_path(reference, group_path),
                    abs_reference
                )

    def test_qualify_reference(self):
        """ Ensure that a reference within a variable's metadata is correctly
            qualified to an absolute variable path, using the nature of the
            reference (e.g. prefix of "../" or "./") and the group of the
            referee variable.

        """
        dataset = Dataset('test.nc', 'w', diskless=True)
        dataset.createDimension('lat', size=2)
        dataset.createDimension('lon', size=4)

        data = np.ones((2, 4))
        variable = dataset.createVariable('/group/variable', data.dtype,
                                          dimensions=('lat', 'lon'))

        dataset.createVariable('/group/sibling', data.dtype,
                               dimensions=('lat', 'lon'))

        test_args = [
            ['In /group/variable, ref /base_var', '/base_var', '/base_var'],
            ['In /group/variable, ref ../base_var', '../base_var', '/base_var'],
            ['In /group/variable, ref ./group_var', './group_var', '/group/group_var'],
            ['In /group/variable, ref sibling', 'sibling', '/group/sibling'],
            ['In /group/variable, ref non-sibling', 'non_sibling', '/non_sibling']
        ]

        for description, raw_reference, absolute_reference in test_args:
            with self.subTest(description):
                self.assertEqual(qualify_reference(raw_reference, variable),
                                 absolute_reference)

        dataset.close()

    def test_variable_in_dataset(self):
        """ Ensure that a variable will be correctly identified as belonging
            to the dataset. Also, the function should successfully handle
            absent intervening groups.

        """
        dataset = Dataset('test.nc', 'w', diskless=True)
        dataset.createDimension('lat', size=2)
        dataset.createDimension('lon', size=4)

        data = np.ones((2, 4))

        dataset.createVariable('/group/variable', data.dtype,
                               dimensions=('lat', 'lon'))
        dataset.createVariable('/group/group_two/variable_two', data.dtype,
                               dimensions=('lat', 'lon'))
        dataset.createVariable('/base_variable', data.dtype,
                               dimensions=('lat', 'lon'))

        test_args = [
            ['Root variable', '/base_variable', True],
            ['Root variable, no leading slash', 'base_variable', True],
            ['Singly nested variable', '/group/variable', True],
            ['Doubly nested variable', '/group/group_two/variable_two', True],
            ['Non existant base variable', '/missing', False],
            ['Non existant nested variable', '/group/missing', False],
            ['Non existant group', '/group_three/variable', False],
            ['Over nested variable', '/group/group_two/group_three/var', False]
        ]

        for description, variable_name, expected_result in test_args:
            with self.subTest(description):
                self.assertEqual(variable_in_dataset(variable_name, dataset),
                                 expected_result)

        dataset.close()

    def test_make_array_two_dimensional(self):
        """ Ensure a 1-D array is expaned to be a 2-D array with elements all
            in the same column,

        """
        input_array = np.array([1, 2, 3])
        expected_output = np.array([[1], [2], [3]])
        output_array = make_array_two_dimensional(input_array)

        self.assertEqual(len(output_array.shape), 2)
        np.testing.assert_array_equal(output_array, expected_output)
