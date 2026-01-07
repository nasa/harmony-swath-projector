import os
from typing import Dict, Optional, Tuple, Union

import numpy as np
from netCDF4 import Dataset, Dimension, Variable
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
    variable: Variable, fill_value: FillValueType, ordered_dims: Tuple[str]
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
    variable_data = variable[:]
    if len(variable_data.shape) == 1:
        return make_array_two_dimensional(variable_data)

    # If the dimensions have been reordered, transpose the variable
    if variable.dimensions != ordered_dims:
        axes = get_axes_permutation(variable.dimensions, ordered_dims)
        variable_data = np.ma.transpose(variable_data, axes=axes)

    return apply_fill(variable_data, fill_value)


def apply_fill(variable_data: np.ma.array, fill_value: FillValueType) -> np.ndarray:
    """Apply fill data of either NaN or the variable's original fill_value.

    A fill value of NaN is applied to Float-64 variables to account for suspected
    issues in Pyresample with float64 fill values (see DAS-2460). For all other data
    types, the original fill value is used.
    """
    if variable_data.dtype == 'float64':
        return variable_data.filled(np.nan)
    return variable_data.filled(fill_value)


def get_coordinate_matching_substring(
    dataset: Dataset, coordinates_tuple: Tuple[str], coordinate_substring
) -> Variable:
    """Search the coordinate dataset names for a match to the substring,
    which will be either "lat" or "lon". Return the corresponding variable
    from the dataset. Only the base variable name is used, as the group
    path may contain either of the strings as part of other words.

    """
    for coordinate in coordinates_tuple:
        if coordinate_substring in coordinate.split('/')[-1] and variable_in_dataset(
            coordinate, dataset
        ):
            return dataset[coordinate]
    raise MissingCoordinatesError(coordinates_tuple)


def get_coordinate_data(
    dataset: Dataset, coordinates_tuple: Tuple[str], coordinate_substring
) -> np.ma.MaskedArray:
    """Return the corresponding coordinate variable data.

    If the variable's track dimensions are determined to require reordering,
    the transposed coordinate variable data is returned.
    """
    coordinate = get_coordinate_matching_substring(
        dataset, coordinates_tuple, coordinate_substring
    )
    if coordinate.ndim == 1:
        return coordinate[:]

    if coordinate_requires_transpose(coordinate):
        return np.ma.transpose(coordinate[:]).copy()
    else:
        return coordinate[:]


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


def get_rows_per_scan(total_rows: int) -> int:
    """
    Finds the smallest divisor of the total number of rows. If no divisor is
    found, return the total number of rows.
    """
    if total_rows < 2:
        return 1
    for row_number in range(2, int(total_rows**0.5) + 1):
        if total_rows % row_number == 0:
            return row_number
    return total_rows


def get_preferred_ordered_dimensions_info(
    variable: Variable, coordinates: Tuple[str], dataset: Dataset
) -> Tuple[tuple[str], list[Dimension]]:
    """Return the variable's dimensions in the preferred order.

    Ensure the track dimensions are the last two dimensions in the tuple and in the
    order of descending size. Any additional dimensions are placed at the front of the
    tuple maintaining the oringinal relative order between themselves.
    """
    # Either 'lat' or 'lon' could be used as the substring here
    coordinate_var = get_coordinate_matching_substring(dataset, coordinates, 'lat')
    ordered_track_dims = get_ordered_track_dims(coordinate_var)

    current_dims = variable.dimensions

    # Ensure both required dims are present
    if not all(dim in current_dims for dim in ordered_track_dims):
        raise Exception(f"Invalid dimensions {current_dims} for reprojection")

    ordered_non_track_dims = [
        dim for dim in current_dims if dim not in ordered_track_dims
    ]

    all_ordered_dims = (*ordered_non_track_dims, *ordered_track_dims)

    ordered_non_track_dim_objs = [
        dataset.dimensions[dim] for dim in ordered_non_track_dims
    ]

    return all_ordered_dims, ordered_non_track_dim_objs


def get_ordered_track_dims(coordinate_var: Variable) -> Tuple[str]:
    """
    Return track dimensions in order of descending size.
    """
    if not coordinate_var.ndim == 2:
        raise Exception('Unsupported coordinate variable shape')
    if coordinate_requires_transpose(coordinate_var):
        return coordinate_var.dimensions[::-1]
    else:
        return coordinate_var.dimensions


def get_axes_permutation(old_dims: Tuple[str], new_dims: Tuple[str]) -> Tuple[int]:
    """
    Compute the axis permutation required to reorder dimension array.
    """
    axes = []
    used = [False] * len(old_dims)

    for new_dim in new_dims:
        for i, old_dim in enumerate(old_dims):
            if old_dim == new_dim and not used[i]:
                axes.append(i)
                used[i] = True
                break
    return axes


def coordinate_requires_transpose(coordinate: Variable) -> bool:
    """
    Determine if the given coordinate requires transposal before resampling.

    If a swath has more rows than columns, it should be transposed.
    """
    return coordinate.shape[0] < coordinate.shape[1]
