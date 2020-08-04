from logging import Logger
import os

from netCDF4 import Dataset
from numpy.testing import assert_array_equal

from pymods.nc_merge import (copy_metadata_variable, copy_time_dimension,
                             get_fill_value_from_attributes)
from test.test_utils import TestBase


class TestNCMerge(TestBase):

    @classmethod
    def setUpClass(cls):
        cls.input_file = 'test/data/VNL2_test_data.nc'
        cls.output_file = 'test/data/output.nc'
        cls.logger = Logger('test')

    def tearDown(self):
        if os.path.exists(self.output_file):
            os.remove(self.output_file)

    def test_get_fill_value_from_attributes(self):
        """ If the _FillValue attribute is present, it should be removed from
        the dictionary, and returned as the fill value. Otherwise, a None value
        should be returned.

        """
        with self.subTest('No _FillValue in attributes.'):
            attributes = {'key': 'value'}
            fill_value = get_fill_value_from_attributes(attributes)
            self.assertEqual(fill_value, None)
            self.assertDictEqual(attributes, {'key': 'value'})

        with self.subTest('_FillValue in attributes.'):
            attributes = {'key': 'value', '_FillValue': 100}
            fill_value = get_fill_value_from_attributes(attributes)
            self.assertEqual(fill_value, 100)
            self.assertDictEqual(attributes, {'key': 'value'})

    def test_copy_metadata_variable(self):
        """ Copy a variable from one NETCDF-4 file to another. Ensure that all
            associated attributes are also copied and that the data type is
            maintained.

        """
        variable_name = 'time'

        with Dataset(self.input_file) as in_dataset, \
            Dataset(self.output_file, 'w', format='NETCDF4') as out_dataset:
            # out_dataset.dimensions = in_dataset.dimensions
            copy_metadata_variable(in_dataset, out_dataset, variable_name,
                                   self.logger)
            expected_attributes = in_dataset[variable_name].__dict__
            expected_values = in_dataset[variable_name][:]

        with Dataset(self.output_file) as saved_dataset:
            self.assertTrue(variable_name in saved_dataset.variables)
            self.assertDictEqual(expected_attributes,
                                 saved_dataset[variable_name].__dict__)
            assert_array_equal(expected_values, saved_dataset[variable_name][:])

    def test_copy_time_dimensions(self):
        """ Make sure a time dimension and variable are both created in the
            output dataset.

        """
        with Dataset(self.input_file) as in_dataset, \
            Dataset(self.output_file, 'w', format='NETCDF4') as out_dataset:

            copy_time_dimension(in_dataset, out_dataset, self.logger)
            time_attributes = in_dataset['time'].__dict__
            time_values = in_dataset['time'][:]

        with Dataset(self.output_file) as saved_dataset:
            self.assertTrue('time' in saved_dataset.dimensions)
            self.assertTrue('time' in saved_dataset.variables)
            self.assertDictEqual(time_attributes,
                                 saved_dataset['time'].__dict__)
            assert_array_equal(time_values, saved_dataset['time'][:])
