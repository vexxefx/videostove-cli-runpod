"""
Subprocess wrappers for rclone operations
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional


class RcloneError(Exception):
    """Exception raised for rclone operation failures"""
    pass


def run_rclone_command(args: List[str], capture_output: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    """
    Run an rclone command with proper error handling
    
    Args:
        args: Command arguments starting with rclone subcommand
        capture_output: Whether to capture stdout/stderr
        check: Whether to raise exception on non-zero exit
        
    Returns:
        CompletedProcess result
        
    Raises:
        RcloneError: If command fails and check=True
    """
    cmd = ["rclone"] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=False  # We handle check ourselves for better error messages
        )
        
        if check and result.returncode != 0:
            raise RcloneError(
                f"rclone command failed with exit code {result.returncode}: "
                f"{' '.join(cmd)}\n"
                f"stderr: {result.stderr}"
            )
            
        return result
        
    except FileNotFoundError:
        raise RcloneError("rclone not found. Please install rclone first.")
    except Exception as e:
        raise RcloneError(f"Failed to run rclone command: {e}")


def list_directories(remote_path: str) -> List[str]:
    """
    List directories in a remote path
    
    Args:
        remote_path: Remote path like "gdrive:MyFolder"
        
    Returns:
        List of directory names (not full paths)
        
    Raises:
        RcloneError: If listing fails
    """
    try:
        result = run_rclone_command([
            "lsf", remote_path, "--dirs-only"
        ])
        
        # Parse output - each line is a directory name ending with /
        dirs = []
        for line in result.stdout.strip().split('\n'):
            if line.strip() and line.endswith('/'):
                dirs.append(line.rstrip('/'))
                
        return sorted(dirs)
        
    except RcloneError:
        raise
    except Exception as e:
        raise RcloneError(f"Failed to parse directory listing: {e}")


def list_files(remote_path: str, recursive: bool = False) -> List[str]:
    """
    List files in a remote path
    
    Args:
        remote_path: Remote path like "gdrive:MyFolder"
        recursive: Whether to list recursively
        
    Returns:
        List of file names/paths
        
    Raises:
        RcloneError: If listing fails
    """
    args = ["lsf", remote_path]
    if recursive:
        args.append("-R")
    else:
        args.append("--files-only")
        
    try:
        result = run_rclone_command(args)
        
        files = []
        for line in result.stdout.strip().split('\n'):
            if line.strip() and not line.endswith('/'):
                files.append(line.strip())
                
        return sorted(files)
        
    except RcloneError:
        raise
    except Exception as e:
        raise RcloneError(f"Failed to parse file listing: {e}")


def copy_path(source: str, dest: str, verbose: bool = False) -> None:
    """
    Copy files/directories from source to destination
    
    Args:
        source: Source path (local or remote)
        dest: Destination path (local or remote)
        verbose: Whether to show progress
        
    Raises:
        RcloneError: If copy fails
    """
    args = ["copy", source, dest]
    
    if verbose:
        args.append("-v")
    else:
        args.append("-q")  # Quiet mode
        
    # Always preserve modification times and show stats at the end
    args.extend(["--stats-one-line", "--stats=10s"])
    
    try:
        run_rclone_command(args, capture_output=not verbose)
        
    except RcloneError:
        raise
    except Exception as e:
        raise RcloneError(f"Failed to copy {source} -> {dest}: {e}")


def sync_path(source: str, dest: str, verbose: bool = False, delete: bool = False) -> None:
    """
    Sync source to destination (more efficient than copy for updates)
    
    Args:
        source: Source path (local or remote)
        dest: Destination path (local or remote) 
        verbose: Whether to show progress
        delete: Whether to delete extra files in dest
        
    Raises:
        RcloneError: If sync fails
    """
    args = ["sync", source, dest]
    
    if verbose:
        args.append("-v")
    else:
        args.append("-q")
        
    if delete:
        args.append("--delete-after")
        
    args.extend(["--stats-one-line", "--stats=10s"])
    
    try:
        run_rclone_command(args, capture_output=not verbose)
        
    except RcloneError:
        raise
    except Exception as e:
        raise RcloneError(f"Failed to sync {source} -> {dest}: {e}")


def path_exists(remote_path: str) -> bool:
    """
    Check if a remote path exists
    
    Args:
        remote_path: Remote path to check
        
    Returns:
        True if path exists, False otherwise
    """
    try:
        run_rclone_command(["lsf", remote_path], capture_output=True)
        return True
    except RcloneError:
        return False


def get_rclone_version() -> Optional[str]:
    """
    Get rclone version string
    
    Returns:
        Version string or None if rclone not available
    """
    try:
        result = run_rclone_command(["version", "--check=false"], capture_output=True)
        # Extract version from first line like "rclone v1.64.2"
        first_line = result.stdout.split('\n')[0]
        if 'rclone v' in first_line:
            return first_line.split('rclone v')[1].split()[0]
        return first_line
    except:
        return None