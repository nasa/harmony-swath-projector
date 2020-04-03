import logging
import json
import rasterio
import re
import argparse
from PyMods.reproject import to_object
from netCDF4 import Dataset, ma
import numpy as np

# walk the group tree.
def walktree(top):
    values = top.groups.values()
    yield values
    for value in top.groups.values():
        for children in walktree(value):
            yield children

class NC4Info:
    def __init__(self, ncfile):
        self.rootgroup = Dataset(ncfile)
        self.vars_coord = set()
        self.vars_meta = set()
        self.dims = set()
        self.coords = set()
        self.auxs = set() # auxiliary Information

        for children in walktree(self.rootgroup):
            if self.rootgroup.variables:
                for nvar, var in self.rootgroup.variables.items():
                    if 'coordinates' in var.ncattrs():
                        self.vars_coord.add( "/" + nvar)
                    else:
                        self.vars_meta.add("/" + nvar)
                for dim in self.rootgroup.dimensions:
                    self.dims.add("/" + dim)
            for child in children:
                if child.variables:
                    for varn, var in child.variables.items():
                        if 'coordinates' in var.ncattrs():
                            self.vars_coord.add(child.path + "/" + varn)
                            vcoords = getattr(var, 'coordinates')
                            if not "," in vcoords:
                                self.coords.add(child.path + "/" + getattr(var, 'coordinates'))
                            else:
                                nvc = vcoords.split(", ")
                                for idx, value in enumerate(nvc):
                                    self.coords.add(child.path + "/" + value)
                        else:
                            self.vars_meta.add(child.path + "/" + varn)
                    for dim in child.dimensions:
                        self.dims.add(child.path + "/" + dim)

    def get_sci_vars(self):
        return info4.vars_coord - info4.vars_meta - info4.dims - info4.coords

    def get_meta_vars(self):
        return info4.vars_meta - info4.dims - info4.coords

# Main program start for testing with any input file
#
if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(prog='scan', description='Run NetCDF scaning tool')
    PARSER.add_argument('--file',
                        help='The input file for scanning variables.')
    ARGS = PARSER.parse_args()

    logger = logging.getLogger("SwotRepr")
    syslog = logging.StreamHandler()
    formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s")
    #       "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] [%(user)s] %(message)s")
    syslog.setFormatter(formatter)
    logger.addHandler(syslog)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    input_file = ARGS.file

#----------------------------------------
    info4 = NC4Info(input_file)
    print(info4.rootgroup.data_model)
    sciVars = info4.get_sci_vars()
    print("--------- science_variables ----------")
    print(*(sorted(sciVars)), sep ="\n")
    metaVars = info4.get_meta_vars()
    print("--------- metadata ----------")
    print(*(sorted(metaVars)), sep="\n")


