import os
from typing import Dict, Optional, Tuple, Union

import numpy as np
from netCDF4 import Dataset, Variable
from varinfo import VariableFromNetCDF4

from swath_projector.exceptions import MissingCoordinatesError

FillValueType = Optional[Union[float, int]]


def create_coordinates_key(variable: VariableFromNetCDF4) -> Tuple[str]:
    """Create a unique, hashable entity from the coordinates
    associated with a science variable. These coordinates
    are derived using the `earthdata-varinfo` package, which
    augments the CF-Convention `coordinates` metadata
    attribute with supplements and overrides, where required.

    """
    return tuple(sorted(list(variable.references.get('coordinates'))))


def get_variable_values(
    input_file: Dataset, variable: Variable, fill_value: Optional
) -> np.ndarray:
    """A helper function to retrieve the values of a specified dataset. This
    function accounts for 2-D and 3-D datasets based on whether the time
    variable is present in the dataset.

    As the variable data are returned as a `numpy.ma.MaskedArray`, the will
    return no data in the filled pixels. To ensure that the data are
    correctly handled, the fill value is applied to masked pixels using the
    `filled` method. The variable values are transposed if the `along-track`
    dimension size is less than the `across-track` dimension size.

    """
    # TODO: Remove in favour of apply2D or process_subdimension.
    #       The coordinate dimensions should be determined, and a slice of data
    #       in the longitude-latitude plane should be used to determine 2-D
    #       reprojection information. This information should then also be
    #       applied across the other preceding or following dimensions.
    if len(variable[:].shape) == 1:
        return make_array_two_dimensional(variable[:])
    elif 'time' in input_file.variables and 'time' in variable.dimensions:
        # Assumption: Array = (time, along-track, across-track)
        return transpose_if_xdim_less_than_ydim(variable[0][:]).filled(
            fill_value=fill_value
        )
    else:
        # Assumption: Array = (along-track, across-track)
        return transpose_if_xdim_less_than_ydim(variable[:]).filled(
            fill_value=fill_value
        )


def get_coordinate_variable(
    dataset: Dataset, coordinates_tuple: Tuple[str], coordinate_substring
) -> Optional[np.ma.MaskedArray]:
    """Search the coordinate dataset names for a match to the substring,
    which will be either "lat" or "lon". Return the corresponding variable
    data from the dataset. Only the base variable name is used, as the group
    path may contain either of the strings as part of other words. The
    coordinate variables are transposed if the `along-track`dimension size is
    less than the `across-track` dimension size.

    """
    for coordinate in coordinates_tuple:
        if coordinate_substring in coordinate.split('/')[-1] and variable_in_dataset(
            coordinate, dataset
        ):
            # QuickFix (DAS-2216) for short and wide swaths
            if dataset[coordinate].ndim == 1:
                return dataset[coordinate][:]

            return transpose_if_xdim_less_than_ydim(dataset[coordinate][:])

    raise MissingCoordinatesError(coordinates_tuple)


def get_variable_numeric_fill_value(variable: Variable) -> FillValueType:
    """Retrieve the _FillValue attribute for a given variable. If there is no
    _FillValue attribute, return None. The `pyresample`
    `get_sample_from_neighbour_info` function will only accept numerical
    inputs for `fill_value`. Non-numeric fill values are returned as None.

    This function also accounts for if the input variable is scaled, as the
    fill value as stored in a NetCDF-4 file should match the nature of the
    saved data (e.g., if the data are scaled, the fill value should also
    be scaled).

    """
    if '_FillValue' in variable.ncattrs():
        fill_value = variable.getncattr('_FillValue')
    else:
        fill_value = None

    if not isinstance(fill_value, (np.integer, np.longlong, np.floating, int, float)):
        fill_value = None

    if fill_value is not None:
        scaling = get_scale_and_offset(variable)

        if {'add_offset', 'scale_factor'}.issubset(scaling):
            fill_value = (fill_value * scaling['scale_factor']) + scaling['add_offset']

    return fill_value


def get_variable_file_path(temp_dir: str, variable_name: str, extension: str) -> str:
    """Create a file name for the variable, that should be unique, even if
    there are other variables of the same name in a different group, e.g.:

    /gt1r/land_segments/dem_h
    /gt1l/land_segments/dem_h

    Leading forward slashes will be stripped from the variable name, and
    those within the string are replaced with underscores.

    """
    converted_variable_name = variable_name.lstrip('/').replace('/', '_')
    return os.sep.join([temp_dir, f'{converted_variable_name}{extension}'])


def get_scale_and_offset(variable: Variable) -> Dict:
    """Check the input dataset for the `scale_factor` and `add_offset`
    parameter. If those attributes are present, return a dictionary
    containing those values, so the single band output can correctly scale
    the data. The `netCDF4` package will automatically apply these
    values upon reading and writing of the data.

    """
    attributes = variable.ncattrs()

    if {'add_offset', 'scale_factor'}.issubset(attributes):
        scaling_attributes = {
            'add_offset': variable.getncattr('add_offset'),
            'scale_factor': variable.getncattr('scale_factor'),
        }
    else:
        scaling_attributes = {}

    return scaling_attributes


def qualify_reference(raw_reference: str, variable: Variable) -> str:
    """Take a reference to a variable, as stored in the metadata of another
    variable, and construct an absolute path to it. For example:

    * In '/group_one/var_one', reference: '/base_var' becomes '/base_var'
    * In '/group_one/var_one', reference: '../base_var' becomes '/base_var'
    * In '/group_one/var_one', reference './group_var' becomes
      '/group_one/group_var'
    * In '/group_one/var_one', reference: 'group_var' becomes
      '/group_one/group_var' (if '/group_one' contains 'group_var')
    * In '/group_one/var_one', reference: 'base_var' becomes
      '/base_var' (if'/group_one' does not contain 'base_var')

    """
    referee_group = variable.group()

    if raw_reference.startswith('../'):
        # Reference is relative, and requires qualification
        absolute_reference = construct_absolute_path(raw_reference, referee_group.path)
    elif raw_reference.startswith('/'):
        # Reference is already absolute
        absolute_reference = raw_reference
    elif raw_reference.startswith('./'):
        # Reference is in the same group as this variable
        absolute_reference = referee_group.path + raw_reference[1:]
    elif raw_reference in referee_group.variables:
        # e.g. 'variable_name' and in the referee's group
        absolute_reference = construct_absolute_path(raw_reference, referee_group.path)
    else:
        # e.g. 'variable_name', not in referee's group, assume root group.
        absolute_reference = construct_absolute_path(raw_reference, '')

    return absolute_reference


def construct_absolute_path(reference: str, referee_group_path: str) -> str:
    """Construct an absolute path for a relative reference to another variable
    (e.g. '../latitude'), by combining the reference with the group path of
    the referee variable.

    """
    relative_prefix = '../'
    group_path_pieces = referee_group_path.split('/')

    while reference.startswith(relative_prefix):
        reference = reference[len(relative_prefix) :]
        group_path_pieces.pop()

    absolute_path = '/'.join(group_path_pieces + [reference])

    return f'/{absolute_path.lstrip("/")}'


def variable_in_dataset(variable_name: str, dataset: Dataset) -> bool:
    """Check if a nested variable exists in a NetCDF-4 dataset. This function
    is necessary, as the `Dataset.variables` or `Group.variables` class
    attribute only includes immediate children, not those within nested
    groups.

    """
    variable_pieces = variable_name.lstrip('/').split('/')

    group = dataset
    group_valid = True

    while len(variable_pieces) > 1 and group_valid:
        sub_group = variable_pieces.pop(0)

        if sub_group in group.groups:
            group = group[sub_group]
        else:
            group_valid = False

    return group_valid and variable_pieces[-1] in group.variables


def make_array_two_dimensional(one_dimensional_array: np.ndarray) -> np.ndarray:
    """Take a one dimensional array and make it a two-dimensional array, with
    all values in the same column.

    This is primarily required to allow processing of data with the EWA
    interpolations method.

    """
    return np.expand_dims(one_dimensional_array, 1)


def transpose_if_xdim_less_than_ydim(
    variable_values: np.ma.MaskedArray,
) -> np.ma.MaskedArray:
    """Return transposed variable when variable is wider than tall.

    QuickFix (DAS-2216): We presume that a swath has more rows than columns and
    if that's not the case we transpose it so that it does.
    """
    if len(variable_values.shape) != 2:
        raise ValueError(
            f'Input variable must be 2 dimensional, but got {len(variable_values.shape)} dimensions.'
        )
    if variable_values.shape[0] < variable_values.shape[1]:
        return np.ma.transpose(variable_values).copy()

    return variable_values
