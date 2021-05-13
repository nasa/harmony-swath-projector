""" Reprojection support for merging single-dataset NetCDF-4 files, produced by
    `pyresample`, back into a single output file with all the necessary
    attributes.
"""
from argparse import ArgumentParser
from typing import Dict, Optional, Set, Tuple, Union, Any
import logging
import os
import re
import json
import datetime
from jsonschema import validate

from netCDF4 import Dataset, Variable
import numpy as np

from pymods.exceptions import MissingReprojectedDataError
from pymods.utilities import (get_variable_file_path, qualify_reference,
                              variable_in_dataset)

# Values needed for history_json attribute
HISTORY_JSON_SCHEMA = "https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-0.1.0.json"
PROGRAM = "sds/swot-reproject"
PROGRAM_REF = "https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST"
VERSION = "0.9.0"

def create_history_json(history_att: dict, properties: dict) -> Dict:
    """ Creates json object which is used for history_json attrinute
    in the global attributes of output NetCDF-4.
    """
    new_history: Dict[str, Union[str, Any]] = {}
    new_history["$schema"] = HISTORY_JSON_SCHEMA
    new_history["time"] = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
    new_history["program"] = PROGRAM
    new_history["version"] = VERSION
    new_history["parameters"] = properties
    new_history["derived_from"] = properties["input_file"]
    new_hist_att = new_history["time"] + " " + \
                   new_history["program"] + " " + \
                   new_history["version"] + " " + \
                   new_history["derived_from"]
    if history_att!= "":
        new_history["cf_history"] = history_att
        new_history["cf_history"].append(new_hist_att)
    else:
        new_history["cf_history"] = new_hist_att
    new_history["program_ref"] = PROGRAM_REF

    return new_history

def create_output(properties: dict, output_file: str, temp_dir: str,
                  science_variables: Set[str], metadata_variables: Set[str],
                  logger: logging.Logger) -> None:
    """ Merge the reprojected single-dataset NetCDF-4 files from `pyresample`
        into a single file, copying global attributes and metadata
        variables (those without coordinates, which therefore can't be
        reprojected) from the original input file. Then for each listed science
        variable, retrieve the single-band file and copy the reprojected
        variables, and any accompanying CRS and coordinate variables. Note, the
        coordinate datasets will only be copied once.

    """
    input_file = properties.get("input_file")
    logger.info(f'Creating output file "{output_file}"')

    with Dataset(input_file) as input_dataset, \
         Dataset(output_file, 'w', format='NETCDF4') as output_dataset:
        logger.info('Copying input file attributes to output file.')
        output_dataset.setncatts(read_attrs(input_dataset))

        # Remove properties with None value
        props = {k: v for k, v in properties.items() if v is not None}
        # Remove unparsed by JSON
        if "projection" in  props.keys() : del props["projection"]
        if "x_extent" in  props.keys() : del props["x_extent"]
        if "y_extent" in  props.keys() : del props["y_extent"]
        # Create history_json attribute
        if hasattr(input_dataset,'history'):
            history_att = getattr(input_dataset, "history").split("\n")
        else:
            history_att = ""
        new_history_lst = create_history_json(history_att, props)
        new_history_list = []
        if hasattr(input_dataset, 'history_json'):
            hist_json_att = json.loads(",".join(read_attrs(input_dataset)["history_json"]))
            new_history_list.append(hist_json_att)
        new_history_list.append(new_history_lst)
        json_string = json.dumps(new_history_list)
        output_dataset.setncattr("history_json",json_string)
        # Create history attribute
        if history_att == "":
            new_history_att = str(new_history_lst["cf_history"])
        else:
            new_history_att = "/n".join(new_history_lst["cf_history"])
        output_dataset.setncattr("history", new_history_att)

        if 'time' in input_dataset.dimensions:
            copy_time_dimension(input_dataset, output_dataset, logger)

        for metadata_variable in metadata_variables:
            copy_metadata_variable(input_dataset, output_dataset,
                                   metadata_variable, logger)

        output_extension = os.path.splitext(input_file)[1]

        for variable_name in science_variables:
            dataset_file = get_variable_file_path(temp_dir, variable_name,
                                                  output_extension)

            if os.path.isfile(dataset_file):
                with Dataset(dataset_file) as data:
                    set_dimensions(data, output_dataset)

                    copy_science_variable(input_dataset, output_dataset, data,
                                          variable_name, logger)

                    # Copy supporting variables from the single band output:
                    # the grid mapping, reprojected x and reprojected y.
                    for variable_key in data.variables:
                        if (
                                variable_key not in output_dataset.variables and
                                variable_key != variable_name
                        ):
                            copy_metadata_variable(data, output_dataset,
                                                   variable_key, logger)

            else:
                logger.error(f'Cannot find "{dataset_file}".')
                raise MissingReprojectedDataError(variable_name)


def read_attrs(dataset: Union[Dataset, Variable]) -> Dict:
    """ Read attributes from either a NetCDF4 Dataset or variable object. """
    return dataset.__dict__


def copy_time_dimension(input_dataset: Dataset, output_dataset: Dataset,
                        logger: logging.Logger) -> None:
    """ Add time dimension to the output file. This will first add a dimension,
        before creating the corresponding variable in the output dataset.

    """
    logger.info('Adding "time" dimension.')
    time_variable = input_dataset['time']
    output_dataset.createDimension('time', time_variable.size)
    copy_metadata_variable(input_dataset, output_dataset, 'time', logger)


def set_dimensions(input_dataset: Dataset, output_dataset: Dataset) -> None:
    """ Read the dimensions in the single band intermediate file. Add each
        dimension to the output dataset that is not already present.

    """
    for name, dimension in input_dataset.dimensions.items():
        if name not in output_dataset.dimensions:
            output_dataset.createDimension(name, dimension.size)


def set_metadata_dimensions(metadata_variable: str, source_dataset: Dataset,
                            output_dataset: Dataset) -> None:
    """ Iterate through the dimensions of the metadata variable, and ensure
        that all are present in the reprojected output file. This function is
        necessary if any of the metadata variables, that aren't to be projected
        use the swath-based dimensions from the input granule.

    """
    for dimension in source_dataset[metadata_variable].dimensions:
        if dimension not in output_dataset.dimensions:
            output_dataset.createDimension(
                dimension,
                source_dataset.dimensions[dimension].size
            )


def copy_metadata_variable(source_dataset: Dataset, output_dataset: Dataset,
                           variable_name: str, logger: logging.Logger) -> None:
    """ Write a metadata variable directly from either the input dataset or a
        single band dataset. The variables from the input dataset have not been
        reprojected as they contain no references to coordinate datasets. The
        variables from the single band datasets are the non-science variables,
        e.g. the grid mapping and projected coordinates. In both instances, the
        variable should be exactly copied from the source dataset to the
        output.

    """
    logger.info(f'Adding metadata variable "{variable_name}" to the output.')
    set_metadata_dimensions(variable_name, source_dataset, output_dataset)

    attributes = read_attrs(source_dataset[variable_name])
    fill_value = get_fill_value_from_attributes(attributes)

    output_dataset.createVariable(
        variable_name, source_dataset[variable_name].datatype,
        dimensions=source_dataset[variable_name].dimensions,
        fill_value=fill_value, zlib=True, complevel=6
    )

    output_dataset[variable_name][:] = source_dataset[variable_name][:]
    output_dataset[variable_name].setncatts(attributes)


def copy_science_variable(input_dataset: Dataset, output_dataset: Dataset,
                          single_band_dataset: Dataset, variable_name: str,
                          logger: logging.Logger) -> None:
    """ Write a reprojected variable from a single-band output file to the
        merged output file. This will first obtain metadata (dimensions,
        data type and  attributes) from either the single-band output, or from
        the original input file dataset. Then the variable values from the
        single-band output are copied into the data arrays. If the dataset
        attributes include a scale and offset, the output values are adjusted
        accordingly.

    """
    logger.info(f'Adding reprojected "{variable_name}" to the output')

    dimensions = get_science_variable_dimensions(input_dataset,
                                                 single_band_dataset,
                                                 variable_name)
    attributes = get_science_variable_attributes(input_dataset,
                                                 single_band_dataset,
                                                 variable_name)

    fill_value = get_fill_value_from_attributes(attributes)

    variable = output_dataset.createVariable(
        variable_name, input_dataset[variable_name].datatype,
        dimensions=dimensions, fill_value=fill_value, zlib=True, complevel=6
    )

    # Extract the data from the single band image, and ensure it is correctly
    # scaled, so packing occurs correctly on write.
    raw_data = single_band_dataset[variable_name][:].data
    scale_factor = attributes.get('scale_factor', 1)
    add_offset = attributes.get('add_offset', 0)

    packed_data = (raw_data - add_offset) / scale_factor

    # Make sure the fill value is still correctly scaled
    filled_data = np.where(raw_data == fill_value)
    packed_data[filled_data] = fill_value

    if 'time' in variable.dimensions:
        variable[0, :] = packed_data
    else:
        variable[:] = packed_data

    variable.setncatts(attributes)


def get_science_variable_attributes(input_dataset: Dataset,
                                    single_band_dataset: Dataset,
                                    variable_name: str) -> Dict:
    """ Extract the attributes for a science variable, using a combination of
        the original metadata from the unprojected input variable, and then
        augmenting that with the grid_mapping of the reprojected data. Finally,
        ensure the coordinate metadata are still valid. If not, remove that
        metadata entry.

    """
    variable_attributes = read_attrs(input_dataset[variable_name])
    grid_mapping = single_band_dataset[variable_name].grid_mapping
    variable_attributes['grid_mapping'] = grid_mapping

    if (
            'coordinates' in variable_attributes and
            not check_coor_valid(variable_attributes, variable_name,
                                 input_dataset, single_band_dataset)
    ):
        del variable_attributes['coordinates']

    return variable_attributes


def get_science_variable_dimensions(input_dataset: Dataset,
                                    single_band_dataset: Dataset,
                                    variable_name: str) -> Tuple[str]:
    """ Retrieve the dimensions from the single-band reprojected dataset. If
        the original input dataset has a 'time' dimension, then include that as
        a dimension of the reprojected variable.

    """
    if 'time' not in input_dataset.dimensions:
        dimensions = single_band_dataset[variable_name].dimensions
    else:
        dimensions = ('time',) + single_band_dataset[variable_name].dimensions

    return dimensions


def check_coor_valid(attrs: Dict, variable_name: str, input_dataset: Dataset,
                     single_band_dataset: Dataset) -> bool:
    """ Check if variables listed in the coordinates metadata attributes are
        still valid after reprojection. Invalid coordinate reference cases:

          1) Coordinate variable listed in attribute does not exist in single
             band output dataset.
          2) Coordinate variable array shape in the reprojected, single-band
             dataset does not match the input coordinate array shape.

    """
    coordinates_attribute = attrs.get('coordinates')

    if coordinates_attribute is not None:
        coords = [qualify_reference(coordinate, input_dataset[variable_name])
                  for coordinate
                  in re.split(r'\s+|,\s*', coordinates_attribute)]
    else:
        coords = []

    all_coordinates_in_single_band = all(
        variable_in_dataset(coord, single_band_dataset) for coord in coords
    )

    if not all_coordinates_in_single_band:
        # Coordinates from original variable aren't all present in reprojected
        # output (single band file).
        valid = False
    else:
        valid = all(single_band_dataset[coord].shape == input_dataset[coord].shape
                    for coord in coords)

    return valid


def get_fill_value_from_attributes(variable_attributes: Dict) -> Optional:
    """ Check attributes for _FillValue. If present return the value and
        remove the _FillValue attribute from the input dictionary. Otherwise
        return None.

    """
    return variable_attributes.pop('_FillValue', None)


if __name__ == "__main__":
    PARSER = ArgumentParser(prog='nc_merge',
                            description='Merge reprojected NetCDF4 files into one')
    PARSER.add_argument('--ori-inputfile', dest='ori_inputfile',
                        help='Source NetCDF4 file (before reprojection)')
    PARSER.add_argument('--output-filename', dest='output_filename',
                        help='Merged NetCDF4 output file')
    PARSER.add_argument('--proj-dir', dest='proj_dir',
                        help='Output directory with projected NetCDF4 files')
    PARSER.add_argument('--science-variables', dest='science_variables',
                        help='Variables to include in the merged output file')
    PARSER.add_argument('--metadata-variables', dest='metadata_variables',
                        help='Variables without coordinate references',
                        default=set())
    ARGS = PARSER.parse_args()

    LOGGER = logging.getLogger('nc_merge')
    logging.basicConfig(format='%(asctime)s %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p')

    create_output(ARGS.ori_inputfile, ARGS.output_filename, ARGS.proj_dir,
                  ARGS.science_variables, ARGS.metadata_variables, LOGGER)
