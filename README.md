# devin-package-template
This repo should be used as a template for Python packages and templates.

Most of commands I use here can be found in the `Makefile`, so you can use that as a reference.

+ Environment setup
    + Python Virtual Environments
+ Building
    + Install and uninstall
+ Validation
    + Linting
    + Testing
+ Generate documentation
    + Generate Requirements List
    + Compile Example Notebooks
    + MKDocs-Material Documentation


## Environment Setup

### Python Virtual Environments

Create a new python virtual environment like this.

```bash
python -m venv $(VIRTUAL_ENV_NAME)
```

Activate it like this:

```bash
source $(VIRTUAL_ENV_NAME)/bin/activate
```

It should appear in paranetheses at the beginning of your shell prompt.

Deactivate it using this command:

```bash
deactivate
```
## Builiding the Package

Install the package using this command in the root directory of the package.

```bash
pip install .
```

Uninstall like this.

```bash
pip uninstall $(PACKAGE_NAME)
```

## Validation and Testing

### Testing

I use `pytest` for testing. Run all tests in the `tests/` folder like this.

```bash
cd tests; pytest *.py
```

### Linting

I use `mypy` for linting. Set the Python version in the command.

```bash
python -m mypy $(PACKAGE_SRC) --python-version=3.11
```


## Generate Documentation

### Generate Requirements List

I put requirements lists in the `requrements/`folder. The `freeze` and `list` commands will create a full list of installed packages, where the `pipreqs` command will create a list of only the packages that are used in the project. The `--force` flag will overwrite the file if it already exists.

```bash
mkdir $(REQUIREMENTS_FOLDER)
pip freeze > $(REQUIREMENTS_FOLDER)/requirements.txt	
pip list > $(REQUIREMENTS_FOLDER)/packages.txt
pip install pipreqs
pipreqs --force $(PACKAGE_NAME)/ --savepath $(REQUIREMENTS_FOLDER)/used_packages.txt
```

### Compile Example Notebooks

In the `examples/` folder I usually put notebooks that can be compiled to markdown and included in the documentation shown on the mkdocs website (or even just github). This is done with the following commands.

```bash
jupyter nbconvert --to markdown $(EXAMPLE_NOTEBOOK_FOLDER)/*.ipynb
mv $(EXAMPLE_NOTEBOOK_FOLDER)/*.md $(MKDOCS_FOLDER)
```


### MKDocs-Material Documentation

This template uses the [mkdocs-material](https://squidfunk.github.io/mkdocs-material/) theme to create a website with documentation. All of the Makefile commands startings with "mkdocs" are related to this. See the makefile for available commands.


Use this command to start a new mkdocs project. You'll see that it creates a "mkdocs.yml" file where project info goes. I already created one for this template with the fields I usually put out.

```bash
mkdocs new .
```

Use this command to see a local version of what it will look like

```bash
mkdocs serve
```


This command will publish it to the web.

```bash
mkdocs gh-deploy --force
```

