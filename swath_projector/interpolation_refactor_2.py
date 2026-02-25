def check_variable_projectability(
    dataset: Dataset,
    full_variable: str,
    var_info: VarInfoFromNetCDF4,
    logger: Logger,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Pre-validate whether a variable can be projected.
    
    Recognizes Projectable variables as:
    - VarInfo "science" variables (has spatial-temporal dimensions and coordinates
      or has grid-mapping, but is not itself a coordinate or dimension variable)
    - Has lat/lon coordinates with shared horizontal dimension sizes
    - Lat/Lon coordinates have matching 2D dimensions
    - Those 2D dimensions match adjacent dimensions in the science variable
    
    Note on along-track and across-track dimensions:
    - Lat/Lon coordinates define 2D horizontal dimensions
    - Generally: longer dimension is "along-track" (Y), shorter is "across-track" (X)
    - However, relative sizing is not always reliable
    - If sizes are within nominal % difference, assume Y (along-track) first, X second
    
    Returns:
        Tuple of (is_projectable, reason, details)
        - is_projectable: True if variable can be projected
        - reason: NonProjectableReason constant if not projectable, else None
        - details: Additional details about why variable is not projectable
    """
    variable = dataset[full_variable]
    variable_cf = var_info.get_variable(full_variable)
    
    # Check 1: Must be a VarInfo "science" variable
    # Science variables have coordinates/grid-mapping and are not themselves
    # coordinate or dimension variables
    if not _is_science_variable(full_variable, var_info):
        return (
            False,
            NonProjectableReason.MISSING_COORDINATES,
            "Variable is not classified as a science variable by VarInfo "
            "(metadata, coordinate, or dimension variable)"
        )
    
    # Check 2: Non-numeric data type (cannot be interpolated)
    if not np.issubdtype(variable.dtype, np.number):
        return (
            False,
            NonProjectableReason.NON_NUMERIC_DTYPE,
            f"Variable dtype '{variable.dtype}' is not numeric"
        )
    
    # Check 3: Get and validate coordinates
    coordinates_key = create_coordinates_key(variable_cf)
    if not coordinates_key or len(coordinates_key) == 0:
        return (
            False,
            NonProjectableReason.MISSING_COORDINATES,
            "No coordinate variables found for this variable"
        )
    
    # Check 4: Validate lat/lon coordinates and dimension matching
    return _check_coordinate_dimension_compatibility(
        dataset, variable, full_variable, coordinates_key, logger
    )


def _is_science_variable(full_variable: str, var_info: VarInfoFromNetCDF4) -> bool:
    """Determine if a variable is a VarInfo science variable.
    
    Science variables are defined as:
    - Has spatial-temporal dimensions AND is not a coordinate or dimension variable
    - OR has coordinates attribute
    - OR has grid-mapping attribute
    
    Metadata variables are those not in [science, coordinate, dimension].
    """
    # Check if variable is in VarInfo's science variables set
    science_variables = var_info.get_science_variables()
    return full_variable in science_variables


def _check_coordinate_dimension_compatibility(
    dataset: Dataset,
    variable,
    full_variable: str,
    coordinates_key: Tuple[str],
    logger: Logger,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check that lat/lon coordinates have compatible dimensions with the variable.
    
    Requirements:
    - Lat/Lon coordinates must have matching 2D dimensions
    - Those 2D horizontal dimensions must match adjacent dimensions in the 
      science variable
    
    Along-track (Y) vs Across-track (X) determination:
    - Generally: Y (along-track) is longer, X (across-track) is shorter
    - If dimensions are within ~10% of each other, sizing is not reliable
    - Default assumption: Y (along-track) is first dimension, X is second
    """
    # Find lat/lon coordinate variables
    lat_coord, lon_coord = _find_lat_lon_coordinates(coordinates_key)
    
    if lat_coord is None or lon_coord is None:
        return (
            False,
            NonProjectableReason.MISSING_COORDINATES,
            f"Could not identify lat/lon coordinates from: {coordinates_key}"
        )
    
    try:
        lat_var = dataset[lat_coord]
        lon_var = dataset[lon_coord]
    except KeyError as e:
        return (
            False,
            NonProjectableReason.MISSING_COORDINATES,
            f"Coordinate variable not found in dataset: {e}"
        )
    
    # Check: Lat/Lon must have matching dimensions
    lat_dims = lat_var.dimensions
    lon_dims = lon_var.dimensions
    lat_shape = lat_var.shape
    lon_shape = lon_var.shape
    
    if lat_shape != lon_shape:
        return (
            False,
            NonProjectableReason.DIMENSION_MISMATCH,
            f"Lat/Lon coordinate shapes do not match: lat={lat_shape}, lon={lon_shape}"
        )
    
    if lat_dims != lon_dims:
        return (
            False,
            NonProjectableReason.DIMENSION_MISMATCH,
            f"Lat/Lon coordinate dimensions do not match: lat={lat_dims}, lon={lon_dims}"
        )
    
    # Coordinates should be 1D or 2D for standard swath projection
    coord_ndim = len(lat_shape)
    if coord_ndim == 0:
        return (
            False,
            NonProjectableReason.DIMENSION_MISMATCH,
            "Lat/Lon coordinates are scalar (0-dimensional)"
        )
    
    # Get the horizontal dimension sizes from coordinates
    # For 2D coordinates: shape is (along_track, across_track) typically
    # For 1D coordinates: will be made 2D during processing
    if coord_ndim == 2:
        horizontal_shape = lat_shape  # (Y/along-track, X/across-track)
        horizontal_dims = lat_dims
    elif coord_ndim == 1:
        # 1D coordinates - shape will be expanded to 2D
        horizontal_shape = lat_shape
        horizontal_dims = lat_dims
    else:
        # Coordinates with >2 dimensions are unusual
        logger.debug(
            f"Coordinates have {coord_ndim} dimensions, using last 2 as horizontal"
        )
        horizontal_shape = lat_shape[-2:]
        horizontal_dims = lat_dims[-2:]
    
    # Check: Variable's dimensions must include the horizontal dimensions
    # The horizontal dims should be adjacent in the variable
    var_dims = variable.dimensions
    var_shape = variable.shape
    
    is_compatible, mismatch_details = _check_horizontal_dimension_match(
        var_dims, var_shape, horizontal_dims, horizontal_shape, coord_ndim, logger
    )
    
    if not is_compatible:
        return (
            False,
            NonProjectableReason.DIMENSION_MISMATCH,
            mismatch_details
        )
    
    return (True, None, None)


def _find_lat_lon_coordinates(
    coordinates_key: Tuple[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Find latitude and longitude coordinate variable names from coordinates key.
    
    Returns:
        Tuple of (lat_coord_name, lon_coord_name)
    """
    lat_coord = None
    lon_coord = None
    
    for coord in coordinates_key:
        coord_lower = coord.lower()
        coord_base = coord_lower.split('/')[-1]  # Handle paths like /group/latitude
        
        if lat_coord is None and any(
            pattern in coord_base for pattern in ['lat', 'latitude']
        ):
            lat_coord = coord
        elif lon_coord is None and any(
            pattern in coord_base for pattern in ['lon', 'longitude']
        ):
            lon_coord = coord
    
    return lat_coord, lon_coord


def _check_horizontal_dimension_match(
    var_dims: Tuple[str],
    var_shape: Tuple[int],
    horizontal_dims: Tuple[str],
    horizontal_shape: Tuple[int],
    coord_ndim: int,
    logger: Logger,
) -> Tuple[bool, str]:
    """Check that variable dimensions are compatible with coordinate horizontal dimensions.
    
    For projection, the variable must have dimensions that match the coordinate
    dimensions. The horizontal dimensions should appear as adjacent dimensions
    in the variable (typically the last N dimensions where N is the coordinate
    dimensionality).
    
    Along-track vs Across-track heuristic:
    - If dimension sizes differ significantly: larger is along-track (Y)
    - If within ~10% (NOMINAL_PERCENT_DIFFERENCE): assume order is (Y, X)
    
    Returns:
        Tuple of (is_compatible, error_details)
    """
    NOMINAL_PERCENT_DIFFERENCE = 0.10  # 10% threshold for size comparison
    
    if len(var_shape) < coord_ndim:
        return (
            False,
            f"Variable has fewer dimensions ({len(var_shape)}) than "
            f"coordinates ({coord_ndim})"
        )
    
    # Strategy 1: Check by dimension names (preferred)
    if horizontal_dims and all(dim in var_dims for dim in horizontal_dims):
        # Find positions of horizontal dims in variable
        dim_positions = [var_dims.index(dim) for dim in horizontal_dims]
        
        # Check if dimensions are adjacent
        if len(dim_positions) == 2:
            if abs(dim_positions[1] - dim_positions[0]) != 1:
                return (
                    False,
                    f"Horizontal dimensions {horizontal_dims} are not adjacent "
                    f"in variable dimensions {var_dims}"
                )
        
        # Verify shapes match
        for dim in horizontal_dims:
            dim_idx = var_dims.index(dim)
            coord_dim_idx = horizontal_dims.index(dim) if dim in horizontal_dims else -1
            if coord_dim_idx >= 0 and coord_dim_idx < len(horizontal_shape):
                if var_shape[dim_idx] != horizontal_shape[coord_dim_idx]:
                    return (
                        False,
                        f"Dimension '{dim}' size mismatch: variable has "
                        f"{var_shape[dim_idx]}, coordinates have "
                        f"{horizontal_shape[coord_dim_idx]}"
                    )
        
        logger.debug(
            f"Dimension match by name: var_dims={var_dims}, "
            f"horizontal_dims={horizontal_dims}"
        )
        return (True, "")
    
    # Strategy 2: Check by shape matching (fallback for 2D coordinates)
    if coord_ndim >= 2:
        # Variable's last 2 dimensions should match coordinate shape
        var_horizontal_shape = var_shape[-2:]
        
        if var_horizontal_shape == horizontal_shape:
            logger.debug(
                f"Dimension match by shape: var_shape[-2:]={var_horizontal_shape} "
                f"matches coord_shape={horizontal_shape}"
            )
            return (True, "")
        
        # Check if shapes match in reverse order (X, Y vs Y, X)
        if var_horizontal_shape == horizontal_shape[::-1]:
            logger.debug(
                f"Dimension match by reversed shape: var_shape[-2:]="
                f"{var_horizontal_shape} matches reversed coord_shape"
            )
            return (True, "")
        
        # Log along-track/across-track analysis for debugging
        if len(horizontal_shape) == 2:
            y_size, x_size = horizontal_shape
            if y_size > 0 and x_size > 0:
                size_diff_ratio = abs(y_size - x_size) / max(y_size, x_size)
                if size_diff_ratio <= NOMINAL_PERCENT_DIFFERENCE:
                    logger.debug(
                        f"Along-track/across-track sizes within {NOMINAL_PERCENT_DIFFERENCE*100}% "
                        f"({y_size} vs {x_size}), assuming Y-first order"
                    )
        
        return (
            False,
            f"Variable spatial dimensions {var_horizontal_shape} do not match "
            f"coordinate dimensions {horizontal_shape}"
        )
    
    # Strategy 3: For 1D coordinates, check that variable has at least that dimension
    if coord_ndim == 1:
        coord_size = horizontal_shape[0]
        if coord_size in var_shape:
            logger.debug(
                f"1D coordinate size {coord_size} found in variable shape {var_shape}"
            )
            return (True, "")
        
        return (
            False,
            f"1D coordinate size {coord_size} not found in variable shape {var_shape}"
        )
    
    return (
        False,
        f"Could not validate dimension compatibility: var_dims={var_dims}, "
        f"horizontal_dims={horizontal_dims}"
    )



def check_variable_projectability(
    dataset: Dataset,
    full_variable: str,
    var_info: VarInfoFromNetCDF4,
    logger: Logger,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Pre-validate whether a variable can be projected.
    
    Checks for known non-projectable conditions before attempting projection:
    1. Dimension mismatch with coordinate variables
    2. Non-numeric data types
    3. Missing coordinate references
    
    Returns:
        Tuple of (is_projectable, reason, details)
        - is_projectable: True if variable can be projected
        - reason: NonProjectableReason constant if not projectable, else None
        - details: Additional details about why variable is not projectable
    """
    variable = dataset[full_variable]
    variable_cf = var_info.get_variable(full_variable)
    metadata_variables = var_info.get_metadata_variables()

    requested_variables = var_info.get_science_variables().union(metadata_variables)

    # Check 1: Non-numeric data type
    if not np.issubdtype(variable.dtype, np.number):
        return (
            False,
            NonProjectableReason.NON_NUMERIC_DTYPE,
            f"Variable dtype '{variable.dtype}' is not numeric"
        )

    print(f'\nfull_variable: {full_variable}')
    # print(f'{full_variable}.is_geographic(): {var_info.get_variable(full_variable).is_geographic()}')
    # print(f'{full_variable}.is_projection_x_or_y(): {var_info.get_variable(full_variable).is_projection_x_or_y()}')
    #print(f'{full_variable}.is_temporal(): {var_info.get_variable(full_variable).is_temporal()}')

    # Check 2: Missing coordinates
    coordinates_key = create_coordinates_key(variable_cf)
    if not coordinates_key or len(coordinates_key) == 0:
        return (
            False,
            NonProjectableReason.MISSING_COORDINATES,
            "No coordinate variables found for this variable"
        )

    # Check 3: Dimension mismatch with coordinates
    try:
        latitudes_coor = get_coordinate_matching_substring(
            dataset,
            coordinates_key,
            'lat'
        )

        all_ordered_dims, ordered_non_track_dim_objs = (
             get_preferred_ordered_dimensions_info(variable, coordinates_key, dataset)
        )

        print(f'all_ordered_dims: {all_ordered_dims}')
        print(f'ordered_non_track_dim_objs: {ordered_non_track_dim_objs}')
        #latitudes = get_coordinate_data(dataset, coordinates_key, 'lat')
        #longitudes = get_coordinate_data(dataset, coordinates_key, 'lon')

        # lat_coord = None
        # lon_coord = None
        # for coord in coordinates_key:
        #    coord_lower = coord.lower()
        #    if 'lat' in coord_lower:
        #        lat_coord = coord
        #    elif 'lon' in coord_lower:
        #        lon_coord = coord
        
        if not latitudes_coor.shape:
            return (
                False,
                NonProjectableReason.MISSING_COORDINATES,
                "No coordinate variables found for this variable"
            )
#        if lat_coord and lon_coord:
#            lat_var = dataset[lat_coord]
#            lon_var = dataset[lon_coord]
#            coord_shape = lat_var.shape
            
        print(f'latitudes.shape: {latitudes_coor.shape}')
        # Variable's last N dimensions should match coordinate shape
        var_spatial_dims = variable.shape[-len(latitudes_coor.shape):]
            
        print(f'variable.shape[-2:]: {variable.shape[-2:]}')
        print(f'variable.shape: {variable.shape}')
        #print(f'coord_shape: {coord_shape}')
        print(f'var_spatial_dims: {var_spatial_dims}')

        if var_spatial_dims != latitudes_coor.shape:
            return (
                False,
                NonProjectableReason.DIMENSION_MISMATCH,
                f"Variable shape {variable.shape} spatial dimensions "
                f"{var_spatial_dims} do not match coordinate shape {latitudes_coor.shape}"
            )
    except NonProjectableVariableError as e:
        # Dimension ordering issues indicate non-projectable variable
        dataset.close()
        raise NonProjectableVariableError(
            full_variable,
            NonProjectableReason.DIMENSION_MISMATCH,
            f"Cannot determine dimension ordering: {e}"
        )


    return (True, None, None)

'''
    # Either 'lat' or 'lon' could be used as the substring here
    coordinate_var = get_coordinate_matching_substring(dataset, coordinates_key, dataset)
    ordered_track_dims = get_ordered_track_dims(coordinate_var)

    current_dims = variable.dimensions

    # Ensure both required dims are present
    if not all(dim in current_dims for dim in ordered_track_dims):
        return (
            False,
            NonProjectableReason.DIMENSION_MISMATCH,
            f"Variable shape {variable.shape} spatial dimensions "
            f"Invalid dimensions {current_dims} for reprojection"
        )
'''
