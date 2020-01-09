"""
    Reprojection support for merging single-dataset NetCDF 4 files produced by gdalwarp back
    into a single output file with all the necessary attributes.
"""
import argparse
import logging
import os
import re
import netCDF4
import warnings

GDAL_DATASET_NAME = 'Band1'

coor_info_attrs = {'x': {'long_name': 'x coordinate of projection', 'units': 'm', 'standard_name': 'projection_x_coordinate'},
                   'y': {'long_name': 'y coordinate of projection', 'units': 'm', 'standard_name': 'projection_y_coordinate'}}

def create_output(inputfile, outputfile, temp_dir, logger=None):
    """
        Merging the reprojected single-dataset netCDF4 files from GDAL into one, and copy attributes
        from the original input file
    """

    if not logger:
        logger = logging.getLogger(__name__)
    logger.info("Creating output file '%s'", outputfile)

    with netCDF4.Dataset(inputfile) as inf, netCDF4.Dataset(outputfile, 'w', format='NETCDF4') as out:

        out.setncatts(read_attrs(inf))

        files = [f for f in os.listdir(temp_dir) if f != os.path.basename(outputfile)]
        if has_time_dimension(inf):
            copy_time_dimension(inf, out)

        for file in files:
            logger.info("Adding '%s' to the output", file)
            data = netCDF4.Dataset(temp_dir+'/'+file)
            set_dimension(data, out)

            for name, var in data.variables.items():
                if name not in list(out.variables.keys()):
                    dataset_name = os.path.splitext(file)[0]
                    if name != GDAL_DATASET_NAME:
                        copy_variable(inf, out, data, name, logger)
                    else:
                        copy_variable(inf, out, data, dataset_name, logger)

        # if 'crs' exists in output, rename it to the grid_mapping_name and update grid_mapping attributes
        if 'crs' in out.variables.keys():
            new_crs_name = out['crs'].grid_mapping_name
            out.renameVariable('crs', new_crs_name)
            for name, var in out.variables.items():
                if hasattr(var, 'grid_mapping'):
                    var.grid_mapping = new_crs_name

# read attribute from a file/dataset
def read_attrs(inf):
    return inf.__dict__

# check if coordinates attributes is still valid after reprojection
# Invalud coordinate reference cases:
#    1) coordinate reference no longer exists
#    2) coordinate size does not match after reprojection
def check_coor_valid(attrs, inf, rep):

    coors = re.split(' |,', attrs['coordinates'])
    valid = True

    for coor in coors:
        if coor not in rep.variables.keys():
            valid = False
            break
        elif coor in rep.variables.keys() and coor in inf.variables.keys():
            if rep[coor].shape != inf[coor].shape:
                valid = False
                break

    return valid

# rename 'crs' dataset
def rename_crs(crs):
    return crs.grid_mapping_name

# check if time dimension exists
def has_time_dimension(inf):
    return 'time' in list(inf.dimensions.keys())

# add time dimension to the output file
def copy_time_dimension(inf, out):

    out.createDimension('time', len(inf.dimensions['time']))

# set dimension in the output
def set_dimension(inf, out):

    for name, dimension in inf.dimensions.items():
        if not (dimension.isunlimited() or name in list(out.dimensions.keys())):
            out.createDimension(name, len(dimension))

# get dataset data type, dimensions, and attributes from input
def get_dataset_meta(inf, rep, dataset_name):

    if dataset_name in rep.variables.keys():
        data_type = get_data_type(rep, dataset_name)
        dims = get_dimensions(rep, dataset_name)
        attrs = read_attrs(inf[dataset_name]) if dataset_name in inf.variables.keys() else read_attrs(rep[dataset_name])
        if dataset_name in coor_info_attrs:
            attrs.update(coor_info_attrs[dataset_name])
    else:
        data_type = get_data_type(inf, dataset_name)
        dims = get_dimensions(rep, dataset_name, inf)
        attrs = read_attrs(inf[dataset_name])
        if rep[GDAL_DATASET_NAME].grid_mapping:
            attrs['grid_mapping'] = rep[GDAL_DATASET_NAME].grid_mapping

    # remove coordinates attribute if it is no longer valid
    if 'coordinates' in attrs and not check_coor_valid(attrs, inf, rep):
        del attrs['coordinates']

    return dims, data_type, attrs

# get dimensions from input
def get_dimensions(rep, dataset_name, inf=None):

    if inf:
        if 'time' in list(inf.dimensions.keys()):
            return ('time',) + rep[GDAL_DATASET_NAME].dimensions
        return rep[dataset_name].dimensions

    if rep[dataset_name].size > 1:
        return (dataset_name,)
    return None

# get data type
def get_data_type(inf, dataset_name):
    return inf[dataset_name].datatype

# write dataset value to the output
def copy_variable(inf, out, rep, dataset_name, logger):

    # set data type, dimensions, and attributes
    dims, data_type, attrs = get_dataset_meta(inf, rep, dataset_name)

    if dataset_name not in rep.variables.keys():
        ori_dataset_name = GDAL_DATASET_NAME
    else:
        ori_dataset_name = dataset_name

    if dims:
        out.createVariable(dataset_name, data_type, dims, zlib=True, complevel=6)
    else:
        out.createVariable(dataset_name, data_type, zlib=True, complevel=6)

    out[dataset_name].setncatts(attrs)

    # manually compute the data value if offset and scale_factor exist for integers

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        if rep[ori_dataset_name][:].shape != out[dataset_name].shape:
            reshaped = rep[ori_dataset_name][:].reshape(out[dataset_name].shape)
            if 'add_offset' in attrs and 'scale_factor' in attrs:
                reshaped = reshaped * out[dataset_name].scale_factor + out[dataset_name].add_offset
            out[dataset_name][:] = reshaped
        else:
            out[dataset_name][:] = rep[ori_dataset_name][:]



# main program
if __name__ == "__main__":
    print('Main')
    PARSER = argparse.ArgumentParser(prog='NetCDF4Merger', description='Merged reprojected netcdf4 files into one')
    PARSER.add_argument('--ori-inputfile', dest='ori_inputfile',
                        help='Original input netcdf4 file(before reprojection)')
    PARSER.add_argument('--output-filename', dest='output_filename',
                        help='Merged netcdf4 output file')
    PARSER.add_argument('--proj-dir', dest='proj_dir',
                        help='Output directory where projected netcdf4 files are')
    ARGS = PARSER.parse_args()

    logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

    create_output(ARGS.ori_inputfile, ARGS.output_filename, ARGS.proj_dir)
