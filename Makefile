PACKAGE_NAME = mypkg
PACKAGE_SRC = src/$(PACKAGE_NAME)




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
