from typing import Optional, Tuple, Union
import os
import re

from xarray.core.dataset import Dataset
from xarray.core.variable import Variable
import numpy as np


FillValueType = Optional[Union[float, int]]


def create_coordinates_key(coordinates: str) -> Tuple[str]:
    """ Create a unique, hashable entity from a coordinates attribute in an
        Net-CDF4 file.

    """
    return tuple(re.split(r'\s+|,\s*', coordinates))


def get_variable_values(input_file: Dataset, variable: Variable) -> np.ndarray:
    """ A helper function to retrieve the values of a specified dataset. This
        function accounts for 2-D and 3-D datasets based on whether the time
        variable is present in the dataset.

    """
    # TODO: Remove in favour of apply2D or process_subdimension.
    #       The coordinate dimensions should be determined, and a slice of data
    #       in the longitude-latitude plane should be used to determine 2-D
    #       reprojection information. This information should then also be
    #       applied across the other preceding or following dimensions.
    if input_file.variables.get('time') is not None:
        # Assumption: Array = (1, y, x)
        return variable[0].values
    else:
        # Assumption: Array = (y, x)
        return variable.values


def get_coordinate_variable(dataset: Dataset, coordinates_tuple: Tuple[str],
                            coordinate_substring) -> Optional[Variable]:
    """ Search the coordinate dataset names for a match to the substring,
        which will be either "lat" or "lon". Return the corresponding variable
        from the dataset.

    """
    for coordinate in coordinates_tuple:
        if coordinate_substring in coordinate:
            return dataset.variables.get(coordinate)

    return None


def get_variable_group_and_name(variable: str) -> Tuple[str, str]:
    """ Extract variable name and group from its full path.

        Returns:
            group: String showing location of variable within the NetCDF file.
            name: String name of the variable.

    """
    split_variable = variable.split('/')
    return '/'.join(split_variable[:-1]), split_variable[-1]


def get_variable_numeric_fill_value(variable: Variable) -> FillValueType:
    """ Retrieve the _FillValue attribute for a given variable. If there is no
        _FillValue attribute, return None. The pyresample
        `get_sample_from_neighbour_info` function will only accept numerical
        inputs for `fill_value`. Non-numeric fill values are returned as None.

    """
    fill_value = variable.attrs.get('_FillValue')

    if not isinstance(fill_value,
                      (np.integer, np.long, np.floating, int, float)):
        fill_value = None

    return fill_value


def get_variable_file_path(temp_dir: str, variable_name: str,
                           extension: str) -> str:
    """ Create a file name for the variable, that should be unique, even if
        there are other variables of the same name in a different group, e.g.:

        /gt1r/land_segments/dem_h
        /gt1l/land_segments/dem_h

        Leading forward slashes will be stripped from the variable name, and
        those within the string are replaced with underscores.

    """
    converted_variable_name = variable_name.lstrip('/').replace('/', '_')
    return os.sep.join([temp_dir, f'{converted_variable_name}{extension}'])
