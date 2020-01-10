import logging
import netCDF4
import os
import re
import subprocess
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Mergers import NetCDF4Merger
from test_utils import TestBase

class TestNetCDF4Merger(TestBase):

    input_file = '/home/test/data/VNL2_test_data.nc'
    tmp_dir = '/home/test/data/test_tmp/'
    output_file = '/home/test/data/VNL2_test_data_repr.nc'
    NetCDF4Merger.create_output(input_file, output_file, tmp_dir)

    # TEST CASE: output has all datasets
    #
    def test_output_with_all_datasets(self):
        """Output file has all of the datasets from the input file"""
        num_of_proj_files = len(os.listdir(self.tmp_dir))
        info = subprocess.check_output(['gdalinfo', self.output_file], stderr=subprocess.STDOUT).decode("utf-8")
        datasets = [line.split('=')[-1] for line in info.split("\n") if re.match(r"^\s*SUBDATASET_\d+_NAME=", line)]
        num_of_datasets = len(datasets)
        # output would have three more datasets then the number of file (lat, lon, crs)
        self.assertEqual(num_of_datasets, num_of_proj_files, "Should be equal")

    # TEST CASE: datasets in the output file should have same dimension size as the ones in the input
    #
    def test_same_dimension(self):
        """Datasets in input and output should have same number of dimensions"""
        test_dataset = 'sea_surface_temperature.nc'
        test_file = netCDF4.Dataset(self.tmp_dir+test_dataset)
        inf = netCDF4.Dataset(self.input_file)
        out = netCDF4.Dataset(self.output_file)
        input_dim = NetCDF4Merger.get_dimensions(test_file, os.path.splitext(test_dataset)[0], inf)
        output_dim = NetCDF4Merger.get_dimensions(test_file, os.path.splitext(test_dataset)[0], out)
        self.assertEqual(len(input_dim), len(output_dim), "Should be equal")

    # TEST CASE: datasets in the output file should have same number of global
    # attributes as the ones in the input
    #
    def test_same_num_of_global_attributes(self):
        """Datasets in input and output should have same number of global attributes"""
        inf = netCDF4.Dataset(self.input_file)
        out = netCDF4.Dataset(self.output_file)
        input_attrs = NetCDF4Merger.read_attrs(inf)
        output_attrs = NetCDF4Merger.read_attrs(out)
        self.assertEqual(len(input_attrs), len(output_attrs), "Should be equal")

    # TEST CASE: datasets in the output file should have same number of attributes as the input file
    #
    def test_same_num_of_dataset_attributes(self):
        """Datasets in input should have one attribute more than the datasets in the input file
            - crs"""
        test_dataset = 'sea_surface_temperature'
        inf = netCDF4.Dataset(self.input_file)
        out = netCDF4.Dataset(self.output_file)
        inf_data = inf[test_dataset]
        out_data = out[test_dataset]
        input_attrs = NetCDF4Merger.read_attrs(inf_data)
        output_attrs = NetCDF4Merger.read_attrs(out_data)
        self.assertEqual(len(input_attrs), len(output_attrs), "Should be equal")

    # TEST CASE: datasets in the output file should have same data type as the ones in the input
    #
    def test_same_data_type(self):
        """Datasets in input and output should have same data type"""
        test_dataset = 'sea_surface_temperature.nc'
        test_file = netCDF4.Dataset(self.tmp_dir + test_dataset)
        inf = netCDF4.Dataset(self.input_file)
        out = netCDF4.Dataset(self.output_file)
        input_data_type = NetCDF4Merger.get_data_type(inf, os.path.splitext(test_dataset)[0])
        output_data_type = NetCDF4Merger.get_data_type(out, os.path.splitext(test_dataset)[0])
        self.assertEqual(input_data_type, output_data_type, "Should be equal")

if __name__ == '__main__':
    unittest.main()
