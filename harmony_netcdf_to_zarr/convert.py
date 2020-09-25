import sys

import numpy as np
import zarr
from netCDF4 import Dataset


def netcdf_to_zarr(src, dst):
    """
    Convert the NetCDF file at src to the zarr file at dst, preserving data, metadata, and
    group hierarchy


    Parameters
    ----------
    src : string | netCDF4.Dataset
        The file to convert, either a location on disk or an already-opened dataset
    dst : string | collections.MutableMapping
        The output zarr file.  Either a location on disk into which a zarr.DirectoryStore
        will be written or a MutableMapping into which zarr data can be written.
    """
    managed_resources = []
    try:
        # Allow passing in a path to a store or a file
        if isinstance(src, str):
            src = Dataset(src, 'r')
            managed_resources.append(src)

        if isinstance(dst, str):
            dst = zarr.DirectoryStore(dst)
            managed_resources.append(src)

        __copy_group(src, zarr.group(dst, overwrite=True))
        zarr.convenience.consolidate_metadata(dst)

    finally:
        for resource in managed_resources:
            try:
                resource.close()
            except BaseException:
                pass


def __copy_variable(src, dst_group, name):
    """
    Copies the variable from the NetCDF src variable into the Zarr group dst_group, giving
    it the provided name

    Parameters
    ----------
    src : netCDF4.Variable
        the source variable to copy
    dst_group : zarr.hierarchy.Group
        the group into which to copy the variable
    name : string
        the name of the variable in the destination group

    Returns
    -------
    zarr.core.Array
        the copied variable
    """
    chunks = src.chunking()
    if chunks == 'contiguous' or chunks is None:
        chunks = src.shape
    if not chunks and len(src.dimensions) == 0:
        # Treat a 0-dimensional NetCDF variable as a zarr group
        dst = dst_group.create_group(name)
    else:
        dst = dst_group.create_dataset(name,
                                       data=src,
                                       shape=src.shape,
                                       chunks=tuple(chunks),
                                       dtype=src.dtype)

    # xarray requires the _ARRAY_DIMENSIONS metadata to know how to label axes
    __copy_attrs(src, dst, _ARRAY_DIMENSIONS=list(src.dimensions))

    return dst


def __copy_attrs(src, dst, **kwargs):
    """
    Copies all attributes from the source group or variable into the destination group or variable.
    Converts netCDF4 variable values from their native type (typically Numpy dtypes) into
    JSON-serializable values that Zarr can store

    Parameters
    ----------
    src : netCDF4.Group | netCDF4.Variable
        The source from which to copy attributes
    dst : zarr.hierarchy.Group | zarr.core.Array
        The destination into which to copy attributes.
    **kwargs : dict
        Additional attributes to add to the destination
    """
    attrs = {key: __netcdf_attr_to_python(getattr(src, key)) for key in src.ncattrs()}
    attrs.update(kwargs)
    dst.attrs.put(attrs)


def __copy_group(src, dst):
    """
    Recursively copies the source netCDF4 group into the destination Zarr group, along with
    all sub-groups, variables, and attributes

    Parameters
    ----------
    src : netCDF4.Group
        the NetCDF group to copy from
    dst : zarr.hierarchy.Group
        the existing Zarr group to copy into
    """
    __copy_attrs(src, dst)

    for name, item in src.groups.items():
        __copy_group(item, dst.create_group(name.split('/').pop()))

    for name, item in src.variables.items():
        __copy_variable(item, dst, name)


def __netcdf_attr_to_python(val):
    """
    Given an attribute value read from a NetCDF file (typically a numpy type),
    returns the value as a Python primitive type, e.g. np.integer -> int.

    Returns the value unaltered if it does not need conversion or is unrecognized

    Parameters
    ----------
    val : any
        An attribute value read from a NetCDF file

    Returns
    -------
    any
        The converted value
    """
    if isinstance(val, np.integer):
        return int(val)
    elif isinstance(val, np.floating):
        return float(val)
    elif isinstance(val, np.ndarray):
        return [__netcdf_attr_to_python(v) for v in val.tolist()]
    elif isinstance(val, bytes):
        # Assumes bytes are UTF-8 strings.  This holds for attributes.
        return val.decode("utf-8")
    return val


if __name__ == '__main__':
    netcdf_to_zarr(sys.argv[1], sys.argv[2])
