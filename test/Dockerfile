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
	--channel defaults

# Install additional Pip requirements (for SwotRepr itself)
COPY pip_requirements.txt .
RUN conda run --name swotrepr pip install -r pip_requirements.txt

# Install additional Pip requirements (for testing)
COPY ./test/pip_test_requirements.txt test/pip_test_requirements.txt
RUN conda run --name swotrepr pip install -r test/pip_test_requirements.txt

# Bundle app source

COPY ./test test
COPY ./pymods pymods
COPY swotrepr.py .

# Set conda environment to subsetter, as `conda run` will not stream logging.
# Setting these environment variables is the equivalent of `conda activate`.
ENV _CE_CONDA ''
ENV _CE_M ''
ENV CONDA_DEFAULT_ENV swotrepr
ENV CONDA_EXE /opt/conda/bin/conda
ENV CONDA_PREFIX /opt/conda/envs/swotrepr
ENV CONDA_PREFIX_1 /opt/conda
ENV CONDA_PROMPT_MODIFIER (swotrepr)
ENV CONDA_PYTHON_EXE /opt/conda/bin/python
ENV CONDA_ROOT /opt/conda
ENV CONDA_SHLVL 2
ENV PATH "/opt/conda/envs/swotrepr/bin:${PATH}"
ENV SHLVL 1

# Configure a container to be executable via the `docker run` command.
ENTRYPOINT ["/home/test/run"]
