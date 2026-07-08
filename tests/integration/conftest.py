"""Keep the integration *setup* scripts out of pytest collection.

Each case ships a ``setup_integration_test.py`` (downloads the large inputs).
Its ``*_test.py`` suffix matches pytest's default ``python_files``, so pytest
would import both cases' scripts as test modules — and since they share a
basename with no package ``__init__.py``, collection fails with a module-name
clash. They are runnable download scripts, not test modules, so ignore them.
"""

collect_ignore_glob = ["*/setup_integration_test.py"]
