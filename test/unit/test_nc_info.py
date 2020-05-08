from PyMods.nc_info import NCInfo
from test.test_utils import TestBase


class TestNCInfo(TestBase):

    def test_instantiate(self):
        """When given a file name, the `NCInfo` class should successfully
         create a new object with the expected values in the attributes.

        """
        africa = NCInfo('test/data/africa.nc')
        self.assertEqual(africa.ancillary_data, set())
        self.assertEqual(africa.coords, {'lat', 'lon'})
        self.assertEqual(africa.dims, {'ni', 'nj', 'time'})
        self.assertEqual(africa.vars_meta, {'lat', 'lon', 'time'})
        self.assertEqual(africa.vars_with_coords, {'alpha_var', 'blue_var',
                                                   'green_var', 'red_var'})

    def test_get_science_variables(self):
        """Calling the `get_science_variables` method should return the set
        difference between all variables with a coordinates attribute and those
        variables determined to be coordinates or dimensions.

        """
        africa = NCInfo('test/data/africa.nc')
        science_variables = africa.get_science_variables()
        expected_output = {'alpha_var', 'blue_var', 'green_var', 'red_var'}
        self.assertEqual(science_variables, expected_output)

    def test_get_metadata_variables(self):
        """Calling the `get_metadata_variables` method should return the set
        difference between all variables without a coordinate attribute and
        those variables deemed to be coordinates or dimensions.

        """
        africa = NCInfo('test/data/africa.nc')
        metadata_variables = africa.get_metadata_variables()
        self.assertEqual(metadata_variables, set())

    def test_extract_coordinates(self):
        """Ensure a string with either space delimited, comma delimited, or
        comma-space delimited coordinates returns a separated list of these
        coordinate datasets.

        """
        africa = NCInfo('test/data/africa.nc')

        expected_output = ['lon', 'lat']
        test_args = [['space', 'lon lat'],
                     ['multiple spaces', 'lon    lat'],
                     ['comma', 'lon,lat'],
                     ['comma-space', 'lon, lat'],
                     ['comma-multiple-space', 'lon,    lat']]

        for description, coordinates in test_args:
            with self.subTest(description):
                self.assertEqual(africa._extract_coordinates(coordinates),
                                 expected_output)
