from packageurl import PackageURL

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpec, BaseBuildSpecDict


class PyPIBuildSpec(BaseBuildSpec):
    """
    Build specification implementation for PyPI projects.

    Parameters
    ----------
    data : BaseBuildSpecDict
        Dictionary containing the build configuration fields.
    """

    def __init__(self, data: BaseBuildSpecDict):
        """
        Initialize the object.

        Parameters
        ----------
        data : BaseBuildSpecDict
        Dictionary containing the build configuration fields.
        """
        self.data = data

    def resolve_fields(self, purl: PackageURL) -> None:
        """
        Resolve PyPI-specific fields in the build specification.

        Parameters
        ----------
        purl: str
            The target software component Package URL.

        Notes
        -----
        This is an example implementation for demonstration purposes.
        Actual logic for resolving PyPI-specific fields should be included here.
        """
        pass
