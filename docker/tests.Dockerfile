#
# Test image for the Harmony sds/swot-reproject service. This image uses the
# main service image, sds/swot-reproject, as a base layer for the tests. This
# ensures that the contents of the service image are tested, preventing
# discrepancies between the service and test environments.
#
# 2021-06-24: Updated
# 2023-11-16: Updated to use new open-source service image and new conda
#             environment name.
#
FROM ghcr.io/nasa/harmony-swath-projector

ENV PYTHONDONTWRITEBYTECODE=1

# Install additional Pip requirements (for testing)
COPY ./tests/pip_test_requirements.txt tests/pip_test_requirements.txt
RUN conda run --name swathprojector pip install -r tests/pip_test_requirements.txt

# Copy test directory containing Python unittest suite, test data and utilities
COPY ./tests tests

# Set conda environment to subsetter, as `conda run` will not stream logging.
# Setting these environment variables is the equivalent of `conda activate`.
ENV _CE_CONDA='' \
    _CE_M='' \
    CONDA_DEFAULT_ENV=swathprojector \
    CONDA_EXE=/opt/conda/bin/conda \
    CONDA_PREFIX=/opt/conda/envs/swathprojector \
    CONDA_PREFIX_1=/opt/conda \
    CONDA_PROMPT_MODIFIER=(swathprojector) \
    CONDA_PYTHON_EXE=/opt/conda/bin/python \
    CONDA_ROOT=/opt/conda \
    CONDA_SHLVL=2 \
    PATH="/opt/conda/envs/swotrepr/bin:${PATH}" \
    SHLVL=1

# Configure a container to be executable via the `docker run` command.
ENTRYPOINT ["/home/tests/run_tests.sh"]
