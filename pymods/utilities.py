from typing import Dict, Optional, Tuple, Union
import os
import re

from netCDF4 import Dataset, Variable
import numpy as np


FillValueType = Optional[Union[float, int]]


def create_coordinates_key(coordinates: str) -> Tuple[str]:
    """ Create a unique, hashable entity from a coordinates attribute in an
        Net-CDF4 file.

    """
    # TODO: DAS-900 Fully qualify coordinate string
    return tuple(re.split(r'\s+|,\s*', coordinates))


def get_variable_values(input_file: Dataset, variable: Variable,
                        fill_value: Optional) -> np.ndarray:
    """ A helper function to retrieve the values of a specified dataset. This
        function accounts for 2-D and 3-D datasets based on whether the time
        variable is present in the dataset.

        As the variable data are returned as a `numpy.ma.MaskedArray`, the will
        return no data in the filled pixels. To ensure that the data are
        correctly handled, the fill value is applied to masked pixels using the
        `filled` method.

    """
    # TODO: Remove in favour of apply2D or process_subdimension.
    #       The coordinate dimensions should be determined, and a slice of data
    #       in the longitude-latitude plane should be used to determine 2-D
    #       reprojection information. This information should then also be
    #       applied across the other preceding or following dimensions.
    if 'time' in input_file.variables:
        # Assumption: Array = (1, y, x)
        return variable[0][:].filled(fill_value=fill_value)
    else:
        # Assumption: Array = (y, x)
        return variable[:].filled(fill_value=fill_value)


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


def get_variable_numeric_fill_value(variable: Variable) -> FillValueType:
    """ Retrieve the _FillValue attribute for a given variable. If there is no
        _FillValue attribute, return None. The pyresample
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

    if not isinstance(fill_value,
                      (np.integer, np.long, np.floating, int, float)):
        fill_value = None

    if fill_value is not None:
        scaling = get_scale_and_offset(variable)

        if {'add_offset', 'scale_factor'}.issubset(scaling):
                fill_value = (
                    (fill_value * scaling['scale_factor'])
                    + scaling['add_offset']
                )

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


def get_scale_and_offset(variable: Variable) -> Dict:
    """ Check the input dataset for the `scale_factor` and `add_offset`
        parameter. If those attributes are present, return a dictionary
        containing those values, so the single band output can correctly scale
        the data. The `netCDF4` package will automatically apply these
        values upon reading and writing of the data.

    """
    attributes = variable.ncattrs()

    if {'add_offset', 'scale_factor'}.issubset(attributes):
        scaling_attributes = {
            'add_offset': variable.getncattr('add_offset'),
            'scale_factor': variable.getncattr('scale_factor')
        }
    else:
        scaling_attributes = {}

    return scaling_attributes
