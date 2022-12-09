# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Import Checks for running and importing from other packages."""

import glob
import os

# All checks have the module name of <name>_check.py.
modules = glob.glob(os.path.join(os.path.dirname(__file__), "*_check.py"))
__all__ = [os.path.basename(f)[:-3] for f in modules if os.path.isfile(f) and not f.endswith("__init__.py")]
