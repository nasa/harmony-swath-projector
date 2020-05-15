FROM continuumio/miniconda3

ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR "/home"

# Bundle app source
COPY ./test test
COPY ./PyMods PyMods
COPY swotrepr.py .
COPY conda_requirements.txt .
COPY pip_requirements.txt .

# Create Conda environment
RUN conda create --name swotrepr --file conda_requirements.txt python=3.7 \
	--channel conda-forge \
	--channel defaults

# Make RUN commands use the Conda environment
SHELL ["conda", "run", "--name", "swotrepr", "/bin/bash", "-c"]

# Install additional Pip requirements (for SwotRepr itself)
RUN pip install -r pip_requirements.txt

# Install additional Pip requirements (for testing)
RUN pip install -r test/pip_test_requirements.txt

ENTRYPOINT ["conda", "run", "--name", "swotrepr", "/home/test/run"]
