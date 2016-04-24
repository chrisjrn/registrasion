Contributing to Registrasion
============================

I'm glad that you're interested in helping make Registrasion better! Thanks! This guide is meant to help make sure your contributions to the project fit in well.

Making a contribution
---------------------

This project makes use of GitHub issues to track pending work, so new features that need implementation can be found there. If you think a new feature needs to be added, raise an issue for discussion before submitting a Pull Request.


Code Style
----------

We use PEP8. Your code should pass checks by ``flake8`` with no errors or warnings before it will be merged.

We use `Google-style docstrings <http://sphinxcontrib-napoleon.readthedocs.org/en/latest/example_google.html>`_, primarily because they're far far more readable than ReST docstrings. New functions should have complete docstrings, so that new contributors have a chance of understanding how the API works.


Structure
---------

Django Models live in ``registrasion/models``; we separate our models out into separate files, because there's a lot of them. Models are grouped by logical functionality.

Actions that operate on Models live in ``registrasion/controllers``.


Testing
-------

Functionality that lives in ``regsistrasion/controllers`` was developed in a test-driven fashion, which is sensible, given it's where most of the business logic for registrasion lives. If you're changing behaviour of a controller, either submit a test with your pull request, or modify an existing test.


Documentation
-------------

Registrasion aims towards high-quality documentation, so that conference registration managers can understand how the system works, and so that webmasters working for conferences understand how the system fits together. Make sure that you have docstrings :)

The documentation is written in Australian English: *-ise* and not *-ize*, *-our* and not *-or*; *vegemite* and not *peanut butter*, etc etc etc.
