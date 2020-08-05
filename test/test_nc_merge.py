import os

import netCDF4

from pymods.nc_info import NCInfo
from pymods.nc_merge import create_output, get_dimensions, read_attrs
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
        create_output(cls.input_file, cls.output_file, cls.tmp_dir,
                      cls.science_variables)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.output_file):
            os.remove(cls.output_file)

    def test_output_has_all_variables(self):
        """ Output file has all expected varaiables from the input file. """
        output_info = NCInfo(self.output_file)
        output_science_variables = output_info.get_science_variables()
        self.assertEqual(len(output_science_variables),
                         len(self.science_variables))

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

    def test_same_number_of_global_attributes(self):
        """ The root group of the input and output files should have same
            number of global attributes.

        """
        in_dataset = netCDF4.Dataset(self.input_file)
        out_dataset = netCDF4.Dataset(self.output_file)
        input_attrs = read_attrs(in_dataset)
        output_attrs = read_attrs(out_dataset)
        self.assertEqual(len(input_attrs), len(output_attrs))

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
        self.assertEqual(input_data_type, output_data_type, "Should be equal")
