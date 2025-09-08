"""
Headless rclone configuration and verification
"""

import base64
import json
import os
from pathlib import Path
from typing import List, Optional

from .config import DEFAULT_RCLONE_CONFIG
from .rclone_io import RcloneError, list_directories, path_exists, get_rclone_version


def materialize_config_from_env() -> bool:
    """
    Create rclone config from environment variables (headless setup)
    
    Supports two modes:
    1. RCLONE_CONFIG_BASE64: Full base64-encoded rclone.conf
    2. RCLONE_DRIVE_SERVICE_ACCOUNT_JSON + RCLONE_REMOTE_NAME: Generate drive config
    
    Returns:
        True if config was created, False if no env vars found
        
    Raises:
        Exception: If config creation fails
    """
    config_path = Path(os.environ.get("RCLONE_CONFIG", DEFAULT_RCLONE_CONFIG))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Method 1: Full base64 config
    if "RCLONE_CONFIG_BASE64" in os.environ:
        try:
            config_data = base64.b64decode(os.environ["RCLONE_CONFIG_BASE64"]).decode('utf-8')
            config_path.write_text(config_data)
            print(f"Created rclone config from RCLONE_CONFIG_BASE64: {config_path}")
            return True
        except Exception as e:
            raise Exception(f"Failed to decode RCLONE_CONFIG_BASE64: {e}")
    
    # Method 2: Service account for Google Drive
    if "RCLONE_DRIVE_SERVICE_ACCOUNT_JSON" in os.environ and "RCLONE_REMOTE_NAME" in os.environ:
        try:
            service_account_data = os.environ["RCLONE_DRIVE_SERVICE_ACCOUNT_JSON"]
            remote_name = os.environ["RCLONE_REMOTE_NAME"]
            
            # Validate service account JSON
            try:
                json.loads(service_account_data)
            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON in RCLONE_DRIVE_SERVICE_ACCOUNT_JSON: {e}")
            
            # Write service account file
            sa_path = config_path.parent / "service-account.json"
            sa_path.write_text(service_account_data)
            
            # Generate rclone config
            config_content = f"""[{remote_name}]
type = drive
service_account_file = {sa_path}
root_folder_id = 
"""
            
            config_path.write_text(config_content)
            print(f"Created rclone config for Google Drive remote '{remote_name}': {config_path}")
            return True
            
        except Exception as e:
            raise Exception(f"Failed to create Google Drive config: {e}")
    
    # No config environment variables found
    if config_path.exists():
        print(f"Using existing rclone config: {config_path}")
        return True
    
    print("No rclone config environment variables found (RCLONE_CONFIG_BASE64 or RCLONE_DRIVE_SERVICE_ACCOUNT_JSON)")
    return False


def verify_remote(remote_base: str) -> bool:
    """
    Verify that a remote path is accessible
    
    Args:
        remote_base: Remote path like "gdrive:MyFolder"
        
    Returns:
        True if remote is accessible, False otherwise
    """
    try:
        # Try to list the remote path
        list_directories(remote_base)
        return True
    except RcloneError as e:
        print(f"Remote verification failed: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error verifying remote: {e}")
        return False


def list_projects(remote_base: str) -> List[str]:
    """
    List project directories in remote, excluding assets and outputs
    
    Args:
        remote_base: Remote base path like "gdrive:MyFolder"
        
    Returns:
        List of project directory names
        
    Raises:
        RcloneError: If listing fails
    """
    try:
        all_dirs = list_directories(remote_base)
        
        # Filter out special directories
        excluded = {"assets", "outputs"}
        projects = [d for d in all_dirs if d not in excluded]
        
        return projects
        
    except RcloneError:
        raise


def pull_shared(remote_base: str, root: Path) -> bool:
    """
    Pull shared assets from remote/assets to root/assets if it exists
    
    Args:
        remote_base: Remote base path
        root: Local root directory
        
    Returns:
        True if assets were pulled, False if no assets found
        
    Raises:
        RcloneError: If pull operation fails
    """
    from .rclone_io import copy_path
    
    remote_assets = f"{remote_base}/assets"
    
    # Check if remote assets exist
    if not path_exists(remote_assets):
        print(f"No shared assets found at {remote_assets}")
        return False
    
    local_assets = root / "assets"
    local_assets.mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"Pulling shared assets: {remote_assets} -> {local_assets}")
        copy_path(remote_assets, str(local_assets), verbose=True)
        print("✅ Shared assets pulled successfully")
        return True
        
    except RcloneError:
        raise


def pull_project(remote_base: str, root: Path, name: str) -> Path:
    """
    Pull a project from remote to local
    
    Args:
        remote_base: Remote base path
        root: Local root directory
        name: Project name
        
    Returns:
        Path to local project directory
        
    Raises:
        RcloneError: If pull operation fails
    """
    from .rclone_io import copy_path
    
    remote_project = f"{remote_base}/{name}"
    local_project = root / name
    
    # Create local project directory
    local_project.mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"Pulling project: {remote_project} -> {local_project}")
        copy_path(remote_project, str(local_project), verbose=True)
        print(f"✅ Project '{name}' pulled successfully")
        return local_project
        
    except RcloneError:
        raise


def push_outputs(remote_base: str, project_dir: Path) -> bool:
    """
    Push project outputs to remote/outputs/<project>/
    
    Args:
        remote_base: Remote base path
        project_dir: Local project directory
        
    Returns:
        True if outputs were pushed, False if no outputs found
        
    Raises:
        RcloneError: If push operation fails
    """
    from .rclone_io import copy_path
    
    local_out = project_dir / "out"
    
    if not local_out.exists() or not any(local_out.iterdir()):
        print(f"No outputs found in {local_out}")
        return False
    
    project_name = project_dir.name
    remote_outputs = f"{remote_base}/outputs/{project_name}"
    
    try:
        print(f"Pushing outputs: {local_out} -> {remote_outputs}")
        copy_path(str(local_out), remote_outputs, verbose=True)
        print(f"✅ Outputs pushed to {remote_outputs}")
        return True
        
    except RcloneError:
        raise


def doctor_rclone() -> dict:
    """
    Check rclone installation and configuration
    
    Returns:
        Dict with diagnostic information
    """
    result = {
        "rclone_available": False,
        "rclone_version": None,
        "config_exists": False,
        "config_path": None,
        "remotes_configured": [],
    }
    
    # Check rclone availability
    version = get_rclone_version()
    if version:
        result["rclone_available"] = True
        result["rclone_version"] = version
    
    # Check config file
    config_path = Path(os.environ.get("RCLONE_CONFIG", DEFAULT_RCLONE_CONFIG))
    result["config_path"] = str(config_path)
    
    if config_path.exists():
        result["config_exists"] = True
        
        # Try to list configured remotes
        try:
            from .rclone_io import run_rclone_command
            cmd_result = run_rclone_command(["listremotes"], capture_output=True)
            remotes = [line.rstrip(':') for line in cmd_result.stdout.strip().split('\n') if line.strip()]
            result["remotes_configured"] = remotes
        except:
            pass
    
    return result