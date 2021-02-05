FROM continuumio/miniconda3

ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR "/home"

# Install dependencies first. These steps take the longest and change the least,
# so their layers should usually be cached
# Run bin/build-test latest --no-delete to take advantage of the faster build

# Create Conda environment
COPY conda_requirements.txt .
RUN conda create -y --name swotrepr --file conda_requirements.txt python=3.7 -q \
	--channel conda-forge \
	--channel defaults && conda clean --all --quiet --yes

# Install additional Pip requirements (for SwotRepr itself)
COPY pip_requirements.txt .
RUN conda run --name swotrepr pip install --no-input -r pip_requirements.txt

# Install additional Pip requirements (for testing)
COPY ./test/pip_test_requirements.txt test/pip_test_requirements.txt
RUN conda run --name swotrepr pip install -r test/pip_test_requirements.txt

# Bundle app source

COPY ./test test
COPY ./pymods pymods
COPY swotrepr.py .

# Set conda environment to subsetter, as `conda run` will not stream logging.
# Setting these environment variables is the equivalent of `conda activate`.
ENV _CE_CONDA='' \
    _CE_M='' \
    CONDA_DEFAULT_ENV=swotrepr \
    CONDA_EXE=/opt/conda/bin/conda \
    CONDA_PREFIX=/opt/conda/envs/swotrepr \
    CONDA_PREFIX_1=/opt/conda \
    CONDA_PROMPT_MODIFIER=(swotrepr) \
    CONDA_PYTHON_EXE=/opt/conda/bin/python \
    CONDA_ROOT=/opt/conda \
    CONDA_SHLVL=2 \
    PATH="/opt/conda/envs/swotrepr/bin:${PATH}" \
    SHLVL=1

# Configure a container to be executable via the `docker run` command.
ENTRYPOINT ["/home/test/run"]
