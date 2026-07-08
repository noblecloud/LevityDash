Documentation for My Project
============================

This folder contains the documentation for My Project. The documentation is generated using Sphinx, a tool that can automatically generate documentation from your Python code's docstrings.

To generate the documentation, follow these steps:

1. Install Sphinx by running the following command:

   .. code-block:: bash

      poetry install --with dev,docs

2. Navigate to the `docs` folder:

   .. code-block:: bash

      cd docs

3. Generate the documentation by running the following command:

   .. code-block:: bash

      make html

   This will generate the documentation in the `_build/html` folder.

4. View the documentation by opening the `_build/html/index.html` file in your web browser.

If you make changes to your code's docstrings, you can regenerate the documentation by running the `make html` command again.

For more information on how to use Sphinx, see the `Sphinx documentation <https://www.sphinx-doc.org/en/master/>`_.