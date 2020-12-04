from shutil import rmtree
from tempfile import mkdtemp
from unittest.mock import Mock

from netCDF4 import Dataset
from pyproj.crs import CRS
from pyresample.geometry import AreaDefinition
import numpy as np

from pymods.nc_single_band import (write_dimensions, write_dimension_variables,
                                   write_grid_mapping, write_science_variable,
                                   write_single_band_output, HARMONY_TARGET)
from test.test_utils import TestBase


class TestNCSingleBand(TestBase):

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = mkdtemp()
        cls.area_id = 'lat, lon'
        cls.area_definition = AreaDefinition.from_extent(cls.area_id,
                                                         '+proj=longlat',
                                                         (2, 4),
                                                         (-5, 40, 5, 50))

        cls.lat_values = np.array([47.5, 42.5])
        cls.lon_values = np.array([-3.75, -1.25, 1.25, 3.75])
        cls.reprojected_data = np.array([[1, 2, 3, 4], [5, 6, 7, 8]])
        cls.variable_name = 'test_variable'
        cls.cache = {('lat', 'lon'): {'dimensions': ('lat', 'lon')}}
        cls.geographic_mapping_attributes = {
            'crs_wkt': cls.area_definition.crs.to_string(),
            'semi_major_axis': 6378137.0,
            'semi_minor_axis': 6356752.314245179,
            'inverse_flattening': 298.257223563,
            'reference_ellipsoid_name': 'WGS 84',
            'longitude_of_prime_meridian': 0.0,
            'prime_meridian_name': 'Greenwich',
            'geographic_crs_name': 'unknown',
            'grid_mapping_name': 'latitude_longitude',
            'towgs84': (0,0, 0.0, 0.0),
        }
        cls.non_geographic_area = AreaDefinition.from_extent(
            'cea', '+proj=cea', (2, 4),
            (-3_000_000, 2_000_000, 3_000_000, 4_000_000)
        )


    @classmethod
    def tearDownClass(cls):
        rmtree(cls.temp_dir)

    def test_write_single_band_output(self):
        """ An overall test that an output file can be produced. This will test
            that each varaible has the expected dimensions, values and
            attributes, and that the overall `netCDF4.Dataset` contains the
            expected dimensions.

        """
        output_path = f'{self.temp_dir}/overall_test.nc'
        write_single_band_output(self.area_definition, self.reprojected_data,
                                 self.variable_name, output_path, self.cache,
                                 {})

        with Dataset(output_path) as saved_output:
            # Check dimensions
            self.assertTupleEqual(tuple(saved_output.dimensions.keys()),
                                  ('lat', 'lon'))
            self.assertEqual(saved_output.dimensions['lat'].size, 2)
            self.assertEqual(saved_output.dimensions['lon'].size, 4)

            # Check all variables are present
            self.assertSetEqual(
                set(saved_output.variables.keys()),
                {'lat', 'lon', 'latitude_longitude', self.variable_name}
            )

            # Check science variable
            np.testing.assert_array_equal(saved_output[self.variable_name][:],
                                          self.reprojected_data)
            self.assertTupleEqual(saved_output[self.variable_name].dimensions,
                                  ('lat', 'lon'))
            self.assertListEqual(saved_output[self.variable_name].ncattrs(),
                                 ['grid_mapping'])
            self.assertEqual(
                saved_output[self.variable_name].getncattr('grid_mapping'),
                'latitude_longitude'
            )

            # Check grid_mapping:
            grid_attributes = saved_output['latitude_longitude'].__dict__
            for attribute_name, attribute_value in grid_attributes.items():
                self.assertEqual(attribute_value,
                                 self.geographic_mapping_attributes[attribute_name])

            # Check dimension variables
            self.assertTupleEqual(saved_output['lat'].dimensions, ('lat',))
            self.assertTupleEqual(saved_output['lon'].dimensions, ('lon',))
            np.testing.assert_array_equal(saved_output['lat'][:], self.lat_values)
            np.testing.assert_array_equal(saved_output['lon'][:], self.lon_values)


    def test_write_dimensions(self):
        """ Ensure dimensions are written with the correct names. The subtests
            should establish whether geographic projections are identified,
            whether pre-existing information in the cache is used and, if
            needed, whether suffices are added to the dimension names.

        """
        with self.subTest('Geographic, Harmony defined area.'):
            cache = {HARMONY_TARGET: {'reprojection': 'information'}}
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dimensions = write_dimensions(dataset, self.area_definition,
                                              cache)

                self.assertTupleEqual(dimensions, ('lat', 'lon'))
                self.assertSetEqual(set(dataset.dimensions.keys()),
                                    {'lat', 'lon'})

        with self.subTest('Non-geographic, Harmony defined area.'):
            cache = {HARMONY_TARGET: {'reprojection': 'information'}}

            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dimensions = write_dimensions(dataset,
                                              self.non_geographic_area, cache)

                self.assertTupleEqual(dimensions, ('y', 'x'))
                self.assertSetEqual(set(dataset.dimensions.keys()),
                                    {'y', 'x'})

        with self.subTest('Geographic, retrieve dimensions from cache.'):
            cache = {('lat', 'lon'): {'dimensions': ('saved_lat', 'saved_lon')}}

            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dimensions = write_dimensions(dataset, self.area_definition,
                                              cache)

                self.assertTupleEqual(dimensions, ('saved_lat', 'saved_lon'))
                self.assertSetEqual(set(dataset.dimensions.keys()),
                                    {'saved_lat', 'saved_lon'})

        with self.subTest('Geographic, no Harmony, but no saved dimensions.'):
            cache = {('lat', 'lon'): {'reprojection': 'information'}}

            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dimensions = write_dimensions(dataset, self.area_definition,
                                              cache)

                self.assertTupleEqual(dimensions, ('lat', 'lon'))
                self.assertSetEqual(set(dataset.dimensions.keys()),
                                    {'lat', 'lon'})

        with self.subTest('Geographic, no Harmony, multiple target grids.'):
            cache = {
                ('first_lat', 'first_lon'): {'dimensions': ('lat', 'lon')},
                ('second_lat', 'second_lon'): {'dimensions': ('lat_1', 'lon_1')},
                ('lat', 'lon'): {}}

            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dimensions = write_dimensions(dataset, self.area_definition,
                                              cache)

                self.assertTupleEqual(dimensions, ('lat_2', 'lon_2'))
                self.assertSetEqual(set(dataset.dimensions.keys()),
                                    {'lat_2', 'lon_2'})

    def test_write_grid_mapping(self):
        """ Check that the grid mapping attributes from the target area are
            saved to the metadata of an appropriately named variable.

            The name of the variable should be returned. If the grid mapping is
            non-standard, and does not include a name, "crs" should be used.
            If the dimensions associated with the mapping do not conform to
            either ('lat', 'lon') or ('y', 'x'), then the extended form of the
            naming schema should be used.

        """
        with self.subTest('Geographic mapping, regular names.'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                grid_mapping_name = write_grid_mapping(dataset, self.area_definition,
                                                       ('lat', 'lon'))

                self.assertEqual(grid_mapping_name, 'latitude_longitude')
                self.assertIn('latitude_longitude', dataset.variables)
                grid_attributes = dataset['latitude_longitude'].__dict__
                for attribute_name, attribute_value in grid_attributes.items():
                    self.assertEqual(
                        attribute_value,
                        self.geographic_mapping_attributes[attribute_name]
                    )

        with self.subTest('Non-geographic mapping, regular names.'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                grid_mapping_name = write_grid_mapping(dataset,
                                                       self.non_geographic_area,
                                                       ('y', 'x'))

                self.assertEqual(grid_mapping_name,
                                 'lambert_cylindrical_equal_area')
                self.assertIn('lambert_cylindrical_equal_area', dataset.variables)
                grid_attributes = dataset['lambert_cylindrical_equal_area'].__dict__
                self.assertIn(grid_attributes['grid_mapping_name'],
                              'lambert_cylindrical_equal_area')

        with self.subTest('Geographic, extended mapping name.'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                grid_mapping_name = write_grid_mapping(dataset,
                                                       self.area_definition,
                                                       ('lat_1', 'lon_1'))

                self.assertEqual(grid_mapping_name,
                                 'latitude_longitude: lat_1 lon_1')
                self.assertIn('latitude_longitude: lat_1 lon_1',
                              dataset.variables)

        with self.subTest('A custom CRS, with no name specified.'):
            crs = Mock(spec=CRS)
            crs.to_cf.return_value = {'grid': 'mapping'}
            area_extent = (-10, -5, 10, 20)
            pixel_size_x = 0.1
            pixel_size_y = 0.1

            target_area = Mock(spec=AreaDefinition, area_extent=area_extent,
                               crs=crs, pixel_size_x=pixel_size_x,
                               pixel_size_y=pixel_size_y)

            with Dataset('test.nc', 'w', diskless=True) as dataset:
                grid_mapping_name = write_grid_mapping(dataset, target_area,
                                                       ('y', 'x'))

                self.assertEqual(grid_mapping_name, 'crs')
                self.assertIn('crs', dataset.variables)

    def test_write_science_variable(self):
        """ Ensure that the values, dimensions, datatype and attributes are all
            correctly set of a science variable. This should also include the
            grid mapping name.

        """
        attributes = {'add_offset': 10, 'scale_factor': 0.1}
        with Dataset('test.nc', 'w', diskless=True) as dataset:
            dataset.createDimension('lat', size=2)
            dataset.createDimension('lon', size=4)

            write_science_variable(dataset, self.reprojected_data,
                                   'science_name', ('lat', 'lon'),
                                   'mapping_name', attributes)

            expected_attributes = {'add_offset': 10,
                                   'grid_mapping': 'mapping_name',
                                   'scale_factor': 0.1}

            # The science variable exists.
            self.assertIn('science_name', dataset.variables)

            # The science variable has the expected data type.
            self.assertEqual(dataset['science_name'].datatype, np.int64)

            # The science variable has the expected dimensions.
            self.assertTupleEqual(dataset['science_name'].dimensions,
                                  ('lat', 'lon'))

            # The science variable array contains the correct values.
            np.testing.assert_array_equal(dataset['science_name'][:],
                                          self.reprojected_data)

            # The science variable metadata attributes are correct.
            self.assertDictEqual(dataset['science_name'].__dict__,
                                 expected_attributes)

    def test_write_dimension_variables(self):
        """ Ensure that dimension variables that have suffices are successfully
            saved to a `netCDF4.Dataset`, and still include the expected
            metadata attributes.

        """
        with Dataset('test.nc', 'w', diskless=True) as dataset:
            dataset.createDimension('lat_1', size=2)
            dataset.createDimension('lon_1', size=4)

            write_dimension_variables(dataset, ('lat_1', 'lon_1'),
                                      self.area_definition)

            # The dimension variables exist.
            self.assertIn('lat_1', dataset.variables)
            self.assertIn('lon_1', dataset.variables)

            # The variables refer to the same named dimensions.
            self.assertTupleEqual(dataset['lat_1'].dimensions, ('lat_1',))
            self.assertTupleEqual(dataset['lon_1'].dimensions, ('lon_1',))

            # The expected attributes are present.
            self.assertDictEqual(
                dataset['lat_1'].__dict__,
                {'long_name': 'latitude',
                 'standard_name': 'latitude',
                 'units': 'degrees_north'}
            )
            self.assertDictEqual(
                dataset['lon_1'].__dict__,
                {'long_name': 'longitude',
                 'standard_name': 'longitude',
                 'units': 'degrees_east'}
            )

            # The data values are correct.
            np.testing.assert_array_equal(dataset['lat_1'][:], self.lat_values)
            np.testing.assert_array_equal(dataset['lon_1'][:], self.lon_values)
