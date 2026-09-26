"""Round-trip packed metadata and coordinate variables through the merger."""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import numpy as np
from netCDF4 import Dataset
from numpy.testing import assert_allclose, assert_array_equal

from swath_projector.nc_merge import (
    copy_dimension_variable,
    copy_metadata_variable,
    create_output,
)


class TestPackedMetadata(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / 'source.nc'
        self.output = Path(self.directory.name) / 'output.nc'
        self.logger = logging.getLogger(__name__)

    def make_source(self, group_path, packing, coordinate=False, dtype='i2'):
        with Dataset(self.source, 'w') as source:
            group = source.createGroup(group_path)
            group.createDimension('sample', 4)
            name = 'sample' if coordinate else 'metadata'
            variable = group.createVariable(
                name, dtype, ('sample',), fill_value=-32768, zlib=True, complevel=6
            )
            variable.setncatts(
                {**packing, 'units': 'seconds', 'long_name': 'Packed values'}
            )
            variable.set_auto_maskandscale(False)
            variable[:] = np.array([0, 2, 4, -32768], dtype=dtype)
        return group_path.rstrip('/') + '/' + name

    def check_copy(self, path, coordinate=False):
        original_bytes = self.source.read_bytes()
        with Dataset(self.source) as source, Dataset(self.output, 'w') as output:
            if coordinate:
                copy_dimension_variable(output, source[path])
            else:
                copy_metadata_variable(source, output, path, self.logger)
            # Reading the source should still use its original scale/mask settings.
            before = source[path][:]
            actual = output[path][:]
            assert_array_equal(np.ma.getmaskarray(actual), np.ma.getmaskarray(before))
            assert_allclose(actual.compressed(), before.compressed())
            self.assertEqual(source[path].__dict__, output[path].__dict__)
            self.assertEqual(source[path].dtype, output[path].dtype)
            self.assertEqual(source[path].dimensions, output[path].dimensions)
            self.assertEqual(output[path].filters()['complevel'], 6)
            self.assertTrue(output[path].filters()['zlib'])
        with Dataset(self.source) as source, Dataset(self.output) as output:
            for variable in (source[path], output[path]):
                variable.set_auto_maskandscale(False)
            assert_array_equal(source[path][:], output[path][:])
        self.assertEqual(self.source.read_bytes(), original_bytes)

    def test_metadata_values_keep_scale_and_offset(self):
        for group in ('/', '/nested/group'):
            for packing in (
                {'scale_factor': 0.5, 'add_offset': 100.0},
                {'scale_factor': 0.125},
                {'add_offset': -10.0},
                {'scale_factor': -0.5, 'add_offset': 10.0},
            ):
                with self.subTest(group=group, packing=packing):
                    path = self.make_source(group, packing)
                    self.check_copy(path)

    def test_coordinate_values_keep_scale_and_offset(self):
        for group in ('/', '/nested/group'):
            for packing in (
                {'scale_factor': 0.5, 'add_offset': 100.0},
                {'scale_factor': 0.125},
                {'add_offset': -10.0},
            ):
                with self.subTest(group=group, packing=packing):
                    path = self.make_source(group, packing, coordinate=True)
                    self.check_copy(path, coordinate=True)

    def test_metadata_copy_also_preserves_its_packed_coordinate(self):
        coordinate = self.make_source(
            '/nested', {'scale_factor': 0.5, 'add_offset': 50.0}, coordinate=True
        )
        with Dataset(self.source, 'a') as source:
            variable = source['nested'].createVariable('metadata', 'f4', ('sample',))
            variable[:] = [1.0, 2.0, 3.0, 4.0]
        self.check_copy('/nested/metadata')
        with Dataset(self.source) as source, Dataset(self.output) as output:
            assert_allclose(
                output[coordinate][:].compressed(), source[coordinate][:].compressed()
            )
            assert_array_equal(
                np.ma.getmaskarray(output[coordinate][:]),
                np.ma.getmaskarray(source[coordinate][:]),
            )

    def test_unpacked_and_identity_packing_values_are_unchanged(self):
        for coordinate in (False, True):
            for packing in ({}, {'scale_factor': 1.0, 'add_offset': 0.0}):
                with self.subTest(coordinate=coordinate, packing=packing):
                    path = self.make_source('/', packing, coordinate=coordinate)
                    self.check_copy(path, coordinate=coordinate)

    def test_create_output_preserves_packed_metadata_and_its_coordinate(self):
        coordinate = self.make_source(
            '/nested', {'scale_factor': 0.5, 'add_offset': 50.0}, coordinate=True
        )
        with Dataset(self.source, 'a') as source:
            variable = source['nested'].createVariable(
                'metadata', 'i2', ('sample',), fill_value=-32768
            )
            variable.setncatts({'scale_factor': 0.25, 'add_offset': 10.0})
            variable.set_auto_maskandscale(False)
            variable[:] = [0, 4, 8, -32768]
        original_bytes = self.source.read_bytes()
        create_output(
            {
                'input_file': str(self.source),
                'granule_url': 'https://example.invalid/source.nc',
            },
            str(self.output),
            self.directory.name,
            set(),
            {'/nested/metadata'},
            self.logger,
            None,
        )
        with Dataset(self.source) as source, Dataset(self.output) as output:
            self.assertIn('history_json', output.ncattrs())
            for path in (coordinate, '/nested/metadata'):
                assert_allclose(
                    output[path][:].compressed(), source[path][:].compressed()
                )
                assert_array_equal(
                    np.ma.getmaskarray(output[path][:]),
                    np.ma.getmaskarray(source[path][:]),
                )
                source[path].set_auto_maskandscale(False)
                output[path].set_auto_maskandscale(False)
                assert_array_equal(output[path][:], source[path][:])
        self.assertEqual(self.source.read_bytes(), original_bytes)

    def test_floating_point_packed_metadata_values_are_preserved(self):
        path = self.make_source(
            '/', {'scale_factor': 0.5, 'add_offset': 100.0}, dtype='f4'
        )
        self.check_copy(path)
