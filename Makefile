PACKAGE_NAME = mediatools
PACKAGE_SRC = src/$(PACKAGE_NAME)

SCRIPTS_PATH = ~/code/media-tools/scripts

MEDIA_DIR = /mnt/MoStorage
SAFARI_DIR = /mnt/MoStorage/safari/shared_album
SAFARI_COMPILATIONS_DIR = /mnt/MoStorage/safari/compilations

GOPRO_DIR = /mnt/MoStorage/gopro/raw_gopro
GOPRO_COMPILATIONS_DIR = /mnt/MoStorage/gopro/compilations

gopro:
	python3 $(SCRIPTS_PATH)/server_v2.py /mnt/MoStorage/gopro $(SCRIPTS_PATH)/templates/gpt_multi_v07_crazy.html --port 8000 -s

montage:
	python3 $(SCRIPTS_PATH)/create_montage_v2.py "$(SAFARI_DIR)/*.mp4" 20 5 "$(SAFARI_COMPILATIONS_DIR)/safari_shared_compilation.mp4" -s 0 -c 1 -v --width 1920 --height 1080
	
#python3 $(SCRIPTS_PATH)/create_montage_v2.py "$(GOPRO_DIR)/GoPro 2025-10-**/GX*.mp4" 120 3 "$(GOPRO_COMPILATIONS_DIR)/safari_and_kuwait2.mp4" -s 2 -c 1 -v --width 3840 --height 2160
#copymontage:
host:
	python3 $(SCRIPTS_PATH)/server_v2.py $(MEDIA_DIR) $(SCRIPTS_PATH)/templates/gpt_multi_v07_crazy.html --port 8000 -s -w


thumbs:
	python3 $(SCRIPTS_PATH)/scan_videos_v1.py "$(MEDIA_DIR)" --make-thumbs


################################## building ##################################
install:
	pip install .

uninstall:
	pip uninstall $(PACKAGE_NAME)


clean_build:
	-rm -r $(PACKAGE_NAME).egg-info
	-rm -r dist
	-rm -r build


################################## testing ##################################
pytest:
	cd tests; pytest *.py

################################## linting ##################################
mypy:
	python -m mypy $(PACKAGE_SRC) --python-version=3.11



################################## Virtual Environments ##################################
activate:
	source $(VIRTUAL_ENV_NAME)/bin/activate

VIRTUAL_ENV_NAME = myenv

venv_new: 
	python -m venv $(VIRTUAL_ENV_NAME)

venv_activate:
	source $(VIRTUAL_ENV_NAME)/bin/activate

venv_deactivate:
	deactivate


################################## Compiling Examples ##################################
EXAMPLE_NOTEBOOK_FOLDER = examples

examples_compile:
	-jupyter nbconvert --to markdown $(EXAMPLE_NOTEBOOK_FOLDER)/*.ipynb
	-mv $(EXAMPLE_NOTEBOOK_FOLDER)/*.md $(MKDOCS_FOLDER)


################################## Make requirements.txt ##################################
REQUIREMENTS_FOLDER = requirements

requirements:
	-mkdir $(REQUIREMENTS_FOLDER)
	pip freeze > $(REQUIREMENTS_FOLDER)/requirements.txt	
	pip list > $(REQUIREMENTS_FOLDER)/packages.txt
	-pip install pipreqs
	pipreqs --force $(PACKAGE_NAME)/ --savepath $(REQUIREMENTS_FOLDER)/used_packages.txt




################################## MKDocs-Material Documentation Website Generation ##################################
# https://squidfunk.github.io/mkdocs-material/
MKDOCS_FOLDER = docs

# https://squidfunk.github.io/mkdocs-material/publishing-your-site/
mkdocs_deploy:
	mkdocs gh-deploy --force

# https://squidfunk.github.io/mkdocs-material/creating-your-site/
mkdocs_serve:
	mkdocs serve

mkdocs_build:
	mkdocs build

# https://squidfunk.github.io/mkdocs-material/getting-started/
mkdocs_setup:
	-pip install mkdocs
	-pip install mkdocs-material
	mkdocs new .
