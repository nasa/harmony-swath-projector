"""This module contains functionality to produce a NetCDF-4 file that should
contain a single science variable and it's associated projected
coordinates. The format of each file should be:

Groups:

- All non-science variables should be in the root group of the NetCDF-4
  dataset.
- The science variable should be in the same location within the output
  dataset as the original input variable was within its dataset.

Variables:

- science variable.
- crs (named according to the CF Conventions).
- x (or lon if geographic).
- y (or lat if geographic).

Dimensions:

- x (or lon if geographic).
- y (or lat if geographic).

"""

from typing import Dict, Tuple

import numpy as np
from netCDF4 import Dataset
from pyresample.geometry import AreaDefinition

DIMENSION_METADATA = {
    'lat': {
        'long_name': 'latitude',
        'standard_name': 'latitude',
        'units': 'degrees_north',
    },
    'lon': {
        'long_name': 'longitude',
        'standard_name': 'longitude',
        'units': 'degrees_east',
    },
    'x': {
        'long_name': 'x coordinate of projection',
        'standard_name': 'projection_x_coordinate',
        'units': 'm',
    },
    'y': {
        'long_name': 'y coordinate of projection',
        'standard_name': 'projection_y_coordinate',
        'units': 'm',
    },
}
HARMONY_TARGET = 'harmony_message_target'


def write_single_band_output(
    target_area: AreaDefinition,
    reprojected_data: np.ndarray,
    variable_name: str,
    variable_output_path: str,
    reprojection_cache: Dict,
    attributes: Dict,
) -> None:
    """The main interface for this module. Each single band output file
    will contain the following properties:

    - A reprojected, 2-dimensional  science variable.
    - Projected x and y dimensions.
    - A 1-dimensional variable for each of the associated dimensions. The
      science variable should use these as its dimensions.
    - A grid mapping variable, with metadata conforming to the CF
      Conventions. The science variable should refer to this in its
      metadata.

    """
    with Dataset(variable_output_path, 'w', format='NETCDF4') as output_file:
        dimensions = write_dimensions(output_file, target_area, reprojection_cache)
        grid_mapping_name = write_grid_mapping(output_file, target_area, dimensions)
        write_science_variable(
            output_file,
            reprojected_data,
            variable_name,
            dimensions,
            grid_mapping_name,
            attributes,
        )
        write_dimension_variables(output_file, dimensions, target_area)


def write_dimensions(
    dataset: Dataset, target_area: AreaDefinition, cache: Dict
) -> Tuple[str]:
    """Derive the dimension names using the target area definition and the
    information available in the reprojection cache. Then write the
    dimensions to the output dataset. Finally, return the dimension names
    for later use; e.g. defining the grid mapping name and writing the
    dimension variables themselves.

    Possible use-cases:

    - The Harmony message fully defines a target area. All science
      variables will use this, and the dimensions can just be ('y', 'x') or
      ('lat', 'lon').
    - The Harmony message does not fully define a target area, but the
      reprojection cache only has one key. The dimensions should be
      ('y', 'x') or ('lat', 'lon').
    - The Harmony message does not fully define a target area, and the
      reprojection cache has multiple keys. This means there are multiple
      target grids. The dimensions for all grids after the first should
      have a suffix added, so that they can all be included in the merged
      output.

    """
    coordinates_key = tuple(target_area.area_id.split(', '))
    grid_mapping_name = target_area.crs.to_cf().get('grid_mapping_name')

    # Identify the base name for the dimensions (geographic or not):
    if grid_mapping_name == 'latitude_longitude':
        x_dim = 'lon'
        y_dim = 'lat'
    else:
        x_dim = 'x'
        y_dim = 'y'

    # Determine whether a suffix is required (e.g. multiple target grids).
    if HARMONY_TARGET not in cache:
        # Use any cached dimensions
        cached_dimensions = cache[coordinates_key].get('dimensions')

        if cached_dimensions is not None:
            y_dim, x_dim = cached_dimensions
        else:
            # Derive suffix
            target_grids = len(cache)

            if target_grids == 1:
                # The first dimensions will be ('y', 'x') or ('lat', 'lon')
                dimension_suffix = ''
            else:
                # Subsequent dimensions will be (y_1, x_1), (y_2, x_2), or
                # ('lat_1', 'lon_1'), ('lat_2', 'lon_2') if geographic.
                dimension_suffix = f'_{str(target_grids - 1)}'

            # Append suffix
            x_dim += dimension_suffix
            y_dim += dimension_suffix

            # Save the dimension information in the cache:
            cache[coordinates_key]['dimensions'] = (y_dim, x_dim)

    dataset.createDimension(y_dim, size=target_area.shape[0])
    dataset.createDimension(x_dim, size=target_area.shape[1])

    return (y_dim, x_dim)


def write_grid_mapping(
    dataset: Dataset, target_area: AreaDefinition, dimensions: Tuple[str]
) -> str:
    """Use the `pyresample.geometry.AreaDefition` instance associated with
    the target area of reprojection to write out a `grid_mapping`
    variable to the single band output `netCDF4.Dataset`.

    Return the grid_mapping name for use as the `grid_mapping_name` of
    the science variable.

    In the instance that there are multiple grids in the output file,
    which would result from multiple input grids, this function will
    use the extended form of `grid_mapping_name`. This format should be:

    '<gridMappingVariable>: <coordinatesVariable> [<coordinatesVariable>]'

    See section 5.6 of the CF-Conventions for more information:

    http://cfconventions.org/cf-conventions/cf-conventions.html

    """
    grid_mapping_attributes = target_area.crs.to_cf()

    if 'grid_mapping_name' not in grid_mapping_attributes:
        grid_mapping_attributes['grid_mapping_name'] = 'crs'

    # Check if there are multiple grids and, if so, use the extended format of
    # grid mapping name.
    if dimensions not in [('lat', 'lon'), ('y', 'x')]:
        grid_mapping_attributes[
            'grid_mapping_name'
        ] += f'_{dimensions[0]}_{dimensions[1]}'

    grid_mapping = dataset.createVariable(
        grid_mapping_attributes['grid_mapping_name'], 'S1'
    )
    grid_mapping.setncatts(grid_mapping_attributes)

    return grid_mapping_attributes.get('grid_mapping_name')


def write_science_variable(
    dataset: Dataset,
    data_values: np.ndarray,
    variable_full_name: str,
    dimensions: Tuple[str],
    grid_mapping_name: str,
    attributes: Dict,
) -> None:
    """Add the science variable to the output `netCDF4.Dataset` instance.
    This variable will require:

    - The reprojected values to be assigned to the variable array.
    - The reprojected dimensions to be associated with the variable.
    - The `grid_mapping_name` to be included as an attribute.
    - Scaling metadata attributes, if present on the input value.

    Note, the `netCDF4` library automatically applied the `add_offset` and
    `scale_factor` keywords on reading and writing of `Variable` objects.

    """
    variable = dataset.createVariable(
        variable_full_name, data_values.dtype, dimensions=dimensions
    )

    attributes['grid_mapping'] = grid_mapping_name
    variable.setncatts(attributes)
    variable[:] = data_values[:]


def write_dimension_variables(
    dataset: Dataset, dimensions: Tuple[str], target_area: AreaDefinition
) -> None:
    """Write projected x and y coordinate information to the `netCDF4.Dataset`
    instance, each as a `netCDF4.Variable`. Each dimension variable
    should have:

    - A 1-dimension array of the projected values of that dimension.
    - A reference to itself as a dimension.
    - Metadata that includes the dimension variable's name and units.

    """
    x_vector, y_vector = target_area.get_proj_vectors()
    dimension_data = {dimensions[0]: y_vector, dimensions[1]: x_vector}

    for dimension_name, dimension_vector in dimension_data.items():
        variable = dataset.createVariable(
            dimension_name, dimension_vector.dtype, dimensions=(dimension_name,)
        )

        variable[:] = dimension_vector

        attributes = next(
            attributes
            for coordinate, attributes in DIMENSION_METADATA.items()
            if dimension_name.startswith(coordinate)
        )

        variable.setncatts(attributes)
