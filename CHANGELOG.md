# Changelog

## [v1.2.1] - 2025-05-09

### Changed

- [[DAS-2216](https://bugs.earthdata.nasa.gov/browse/DAS-2216)]
  The `earthdata-varinfo` configuration file used by the Swath Projector has
  been updated to extend the coverage of TEMPO level 2 collections beyond
  TEMPO_O3_TOT_L2, primarily focusing on TEMPO_NO2_L2 and TEMPO_NO2_L2_NRT.

## [v1.2.0] - 2024-10-10

### Changed

- [[DAS-2216](https://bugs.earthdata.nasa.gov/browse/DAS-2216)]
  The Swath Projector has been updated with quick fixes to add support for TEMPO level 2 data. These changes include optional transposing of arrays based on dimension sizes, addition of rows_per_scan parameter for ewa interpolation, and updates to the configuration file for TEMPO_O3TOT_L2 to correctly locate coordinate variables and exclude science variables with dimensions that do no match those of the coordinate variables.

## [v1.1.1] - 2024-09-16

### Changed

- [[TRT-558](https://bugs.earthdata.nasa.gov/browse/TRT-558)]
  The Swath Projector has been updated to use `earthdata-varinfo` version 3.0.0.
  This update primarily involves the streamlining of the configuration file
  schema. Please see the
  [earthdata-varinfo release notes](https://github.com/nasa/earthdata-varinfo/releases/tag/3.0.0)
  for more information. The configuration file used by the Swath Projector has
  also been renamed to `earthdata_varinfo_config.json`.

## [v1.1.0] - 2024-08-29

### Changed

- [[DAS-1934](https://bugs.earthdata.nasa.gov/browse/DAS-1934)]
  Input parameters that include both both resolutions (`xres` and `yres`) and
  dimenions (`height` and `width`) no longer always raise an exception. An
  exception is raised only when the parameters describe a grid that is not
  internally consistent. [#14](https://github.com/nasa/harmony-swath-projector/pull/14)

## [v1.0.1] - 2024-04-05

This version of the Swath Projector implements black code formatting across the
entire repository. There should be no functional changes to the service.

## [v1.0.0] - 2023-11-16

This version of the Harmony Swath Projector contains all functionality
previously released internally to EOSDIS as `sds/swot-reproject:0.0.4`.
Minor reformatting of the repository structure has occurred to comply with
recommended best practices for a Harmony backend service repository, but the
service itself is functionally unchanged. Additional contents to the repository
include updated documentation and files outlined by the
[NASA open-source guidelines](https://code.nasa.gov/#/guide).

Repository structure changes include:

- Migrating `pymods` directory to `swath_projector`.
- Migrating `swotrepr.py` to `swath_projector/adapter.py`.
- Addition of `swath_projector/main.py`.

For more information on internal releases prior to NASA open-source approval,
see legacy-CHANGELOG.md.

[v1.2.1]: (https://github.com/nasa/harmony-swath-projector/releases/tag/1.2.1)
[v1.2.0]: (https://github.com/nasa/harmony-swath-projector/releases/tag/1.2.0)
[v1.1.1]: (https://github.com/nasa/harmony-swath-projector/releases/tag/1.1.1)
[v1.1.0]: (https://github.com/nasa/harmony-swath-projector/releases/tag/1.1.0)
[v1.0.1]: (https://github.com/nasa/harmony-swath-projector/releases/tag/1.0.1)
[v1.0.0]: (https://github.com/nasa/harmony-swath-projector/releases/tag/1.0.0)
