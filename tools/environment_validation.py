import pkg_resources
import importlib
import os
import sys

from packaging.requirements import Requirement
from packaging.version import parse as parse_version

from pathlib import Path


MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_ENV_PATH = os.path.join(MODULE_DIR, "base.txt")

BASE_ENV = Path(BASE_ENV_PATH).open().read().strip().split("\n")


def validate_libraries(libraries):
    importlib.reload(pkg_resources)
    installed_packages = pkg_resources.working_set
    installed_packages_dict = {i.key: i.version for i in installed_packages}

    installed_packages_list = []
    not_installed_packages_list = []

    for lib in libraries:
        if "_" in lib:
            lib = lib.replace("_", "-")
        lib = lib.lower()
        req = Requirement(lib)
        installed_version = installed_packages_dict.get(req.name)

        if installed_version is None:
            not_installed_packages_list.append(lib)
        else:
            installed_version = parse_version(installed_version)
            if req.specifier.contains(installed_version):
                installed_packages_list.append(lib)
            else:
                not_installed_packages_list.append(lib)

    return installed_packages_list, not_installed_packages_list


def install_libraries(libraries):
    """
    Install libraries using pip's internal API to avoid subprocess security concerns.
    Only installs packages from a predefined whitelist for maximum security.
    """
    import re
    
    # Define a whitelist of commonly used safe packages for this application
    SAFE_PACKAGES = {
        'boto3', 'botocore', 'requests', 'urllib3', 'certifi', 'charset-normalizer',
        'idna', 'python-dateutil', 'six', 'jmespath', 's3transfer', 'packaging',
        'pyparsing', 'setuptools', 'wheel', 'pip', 'rich', 'markdown-it-py',
        'mdurl', 'pygments', 'typing-extensions', 'numpy', 'pandas', 'scipy',
        'matplotlib', 'seaborn', 'jupyter', 'ipython', 'notebook', 'jupyterlab'
    }
    
    # Pattern to match valid Python package names with version specifiers
    valid_package_pattern = re.compile(r'^([a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]?)([<>=!~]+[a-zA-Z0-9._-]+)*$')

    for library_spec in libraries:
        # Strip whitespace
        library_spec = library_spec.strip()
        
        if not library_spec:
            continue
        
        # Extract package name (before any version specifiers)
        package_name_match = re.match(r'^([a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]?)', library_spec)
        if not package_name_match:
            print(f"Skipping invalid package specification: {library_spec}")
            continue
            
        package_name = package_name_match.group(1).lower()
        
        # Check if package is in whitelist
        if package_name not in SAFE_PACKAGES:
            print(f"Skipping non-whitelisted package: {package_name}")
            print(f"If this package is needed, please add it to the SAFE_PACKAGES whitelist")
            continue
        
        # Validate the full specification format
        if not valid_package_pattern.match(library_spec):
            print(f"Skipping invalid package specification format: {library_spec}")
            continue
        
        # Additional safety checks
        if len(library_spec) > 100:
            print(f"Skipping package specification that is too long: {library_spec[:50]}...")
            continue
        
        # Check for suspicious characters
        allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-<>=!~')
        if not all(c in allowed_chars for c in library_spec):
            print(f"Skipping package with suspicious characters: {library_spec}")
            continue

        # Install using pip's internal API (no subprocess needed)
        success = _install_package_safely(library_spec)
        if success:
            print(f"{library_spec} has been installed successfully.")
        else:
            return f"Failed to install {library_spec}"


def _install_package_safely(package_spec):
    """
    Safely install a package using pip's internal API.
    Returns True on success, False on failure.
    """
    try:
        # Try using pip's internal API (preferred method)
        try:
            from pip._internal import main as pip_main
            result = pip_main(['install', '-Uqq', package_spec])
            return result == 0
        except ImportError:
            # Fallback for older pip versions
            import pip
            if hasattr(pip, 'main'):
                result = pip.main(['install', '-Uqq', package_spec])
                return result == 0
            else:
                # If pip API is not available, skip installation
                print(f"Cannot install {package_spec}: pip API not available")
                return False
    except Exception as e:
        print(f"Error installing {package_spec}: {str(e)}")
        return False


def validate_environment(requirements_file="requirements.txt"):

    print("Validating base environment")
    base_installed, base_not_installed = validate_libraries(BASE_ENV)
    install_libraries(base_not_installed)
    print("Base environment validated successfully")

    from rich import print as rprint
    from rich.console import Console

    rprint(
        "[#4cc9f0 bold]Validating environment from requirements.txt[/#4cc9f0 bold] :sparkles:"
    )

    try:
        requirements = Path(requirements_file).open().read().strip().split("\n")
    except FileNotFoundError:
        rprint(
            "[#ef233c]requirements.txt file not found. Please make sure the file exists in the current directory.[/#ef233c]"
        )
        return

    installed, not_installed = validate_libraries(requirements)

    installed_msg = (
        "[#e85d04 underline bold]ENVIRONMENT STATUS[/#e85d04 underline bold]\n"
    )

    for pkg in installed:
        installed_msg += f":white_check_mark: [green] {pkg} is installed[/green]\n"

    for pkg in not_installed:
        installed_msg += f":x: [#ef233c]{pkg} is not installed[/#ef233c]\n"
    rprint(installed_msg)

    if len(not_installed) > 0:
        rprint("[cyan bold]Installing missing libraries[/cyan bold]")
        install_libraries(not_installed)

    rprint(
        "[#a7c957]All required libraries are installed.:tada:\nYou may proceed! :rocket:[/#a7c957]"
    )


def _model_access(model_id):

    import boto3

    session = boto3.Session()
    bedrock_runtime = session.client("bedrock-runtime")

    try:
        bedrock_runtime.invoke_model(modelId=model_id, body="{}")
    except Exception as e:
        if "AccessDeniedException" in str(e):
            return False
        else:
            return True


def validate_model_access(required_models):
    from rich import print as rprint

    validation_msg = (
        "[#e85d04 underline bold]MODEL ACCESS STATUS[/#e85d04 underline bold]\n"
    )
    for model in required_models:
        status = _model_access(model)
        if status:
            validation_msg += (
                f":white_check_mark: [green] {model} is accessible[/green]\n"
            )
        else:
            validation_msg += f":x: [#ef233c]{model} is not accessible[/#ef233c]\n"
    rprint(validation_msg)

    if all([_model_access(model) for model in required_models]):
        rprint(
            "[#a7c957]All required models are accessible.:tada:\nYou may proceed! :rocket:[/#a7c957]"
        )
    else:
        rprint(
            "[#ef233c]Please enable access to the model in the AWS Console as explained in the workshop instructions[/#ef233c]"
        )
