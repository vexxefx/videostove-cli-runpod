"""
Tests for rclone I/O operations with subprocess mocking
"""

import pytest
import subprocess
from unittest.mock import patch, MagicMock

from videostove_cli.rclone_io import (
    run_rclone_command,
    list_directories,
    list_files,
    copy_path,
    sync_path,
    path_exists,
    get_rclone_version,
    RcloneError
)


def test_run_rclone_command_success():
    """Test successful rclone command execution"""
    with patch('subprocess.run') as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = run_rclone_command(["listremotes"])
        
        # Check that subprocess.run was called correctly
        mock_run.assert_called_once_with(
            ["rclone", "listremotes"],
            capture_output=True,
            text=True,
            check=False
        )
        
        assert result.returncode == 0
        assert result.stdout == "success output"


def test_run_rclone_command_failure():
    """Test failed rclone command execution"""
    with patch('subprocess.run') as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"
        mock_run.return_value = mock_result
        
        # Should raise RcloneError when check=True (default)
        with pytest.raises(RcloneError) as exc_info:
            run_rclone_command(["invalid_command"])
        
        assert "error message" in str(exc_info.value)
        
        # Should not raise when check=False
        result = run_rclone_command(["invalid_command"], check=False)
        assert result.returncode == 1


def test_run_rclone_command_not_found():
    """Test rclone command not found"""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = FileNotFoundError()
        
        with pytest.raises(RcloneError) as exc_info:
            run_rclone_command(["listremotes"])
        
        assert "rclone not found" in str(exc_info.value)


def test_list_directories():
    """Test listing directories"""
    mock_output = "dir1/\ndir2/\ndir3/\n"
    
    with patch('videostove_cli.rclone_io.run_rclone_command') as mock_cmd:
        mock_result = MagicMock()
        mock_result.stdout = mock_output
        mock_cmd.return_value = mock_result
        
        dirs = list_directories("remote:path")
        
        # Check command was called correctly
        mock_cmd.assert_called_once_with([
            "lsf", "remote:path", "--dirs-only"
        ])
        
        # Check results
        assert dirs == ["dir1", "dir2", "dir3"]
        
        # Test empty output
        mock_result.stdout = ""
        dirs = list_directories("remote:path")
        assert dirs == []


def test_list_files():
    """Test listing files"""
    mock_output = "file1.txt\nfile2.jpg\nfile3.mp4\n"
    
    with patch('videostove_cli.rclone_io.run_rclone_command') as mock_cmd:
        mock_result = MagicMock()
        mock_result.stdout = mock_output
        mock_cmd.return_value = mock_result
        
        # Test non-recursive
        files = list_files("remote:path")
        
        mock_cmd.assert_called_once_with([
            "lsf", "remote:path", "--files-only"
        ])
        
        assert files == ["file1.txt", "file2.jpg", "file3.mp4"]
        
        # Test recursive
        mock_cmd.reset_mock()
        files = list_files("remote:path", recursive=True)
        
        mock_cmd.assert_called_once_with([
            "lsf", "remote:path", "-R"
        ])


def test_copy_path():
    """Test copying paths"""
    with patch('videostove_cli.rclone_io.run_rclone_command') as mock_cmd:
        mock_result = MagicMock()
        mock_cmd.return_value = mock_result
        
        # Test basic copy
        copy_path("source", "dest")
        
        expected_args = [
            "copy", "source", "dest", "-q", 
            "--stats-one-line", "--stats=10s"
        ]
        mock_cmd.assert_called_once_with(expected_args, capture_output=True)
        
        # Test verbose copy
        mock_cmd.reset_mock()
        copy_path("source", "dest", verbose=True)
        
        expected_args = [
            "copy", "source", "dest", "-v",
            "--stats-one-line", "--stats=10s"
        ]
        mock_cmd.assert_called_once_with(expected_args, capture_output=False)


def test_sync_path():
    """Test syncing paths"""
    with patch('videostove_cli.rclone_io.run_rclone_command') as mock_cmd:
        mock_result = MagicMock()
        mock_cmd.return_value = mock_result
        
        # Test basic sync
        sync_path("source", "dest")
        
        expected_args = [
            "sync", "source", "dest", "-q",
            "--stats-one-line", "--stats=10s"
        ]
        mock_cmd.assert_called_once_with(expected_args, capture_output=True)
        
        # Test sync with delete
        mock_cmd.reset_mock()
        sync_path("source", "dest", delete=True)
        
        expected_args = [
            "sync", "source", "dest", "-q", "--delete-after",
            "--stats-one-line", "--stats=10s"
        ]
        mock_cmd.assert_called_once_with(expected_args, capture_output=True)


def test_path_exists():
    """Test checking if path exists"""
    with patch('videostove_cli.rclone_io.run_rclone_command') as mock_cmd:
        # Test existing path
        mock_cmd.return_value = MagicMock()
        
        exists = path_exists("remote:existing")
        assert exists == True
        
        mock_cmd.assert_called_once_with(
            ["lsf", "remote:existing"], 
            capture_output=True
        )
        
        # Test non-existing path (raises RcloneError)
        mock_cmd.side_effect = RcloneError("not found")
        
        exists = path_exists("remote:missing")
        assert exists == False


def test_get_rclone_version():
    """Test getting rclone version"""
    with patch('videostove_cli.rclone_io.run_rclone_command') as mock_cmd:
        # Test successful version check
        mock_result = MagicMock()
        mock_result.stdout = "rclone v1.64.2\nsome other info\n"
        mock_cmd.return_value = mock_result
        
        version = get_rclone_version()
        assert version == "1.64.2"
        
        mock_cmd.assert_called_once_with(
            ["version", "--check=false"], 
            capture_output=True
        )
        
        # Test failure
        mock_cmd.side_effect = RcloneError("command failed")
        
        version = get_rclone_version()
        assert version is None


def test_rclone_error_handling():
    """Test RcloneError exception handling"""
    # Test error message construction
    error = RcloneError("test error")
    assert str(error) == "test error"
    
    # Test in context of run_rclone_command
    with patch('subprocess.run') as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "command failed"
        mock_run.return_value = mock_result
        
        with pytest.raises(RcloneError) as exc_info:
            run_rclone_command(["test"])
        
        error_msg = str(exc_info.value)
        assert "command failed" in error_msg
        assert "exit code 1" in error_msg


def test_command_construction():
    """Test that rclone commands are constructed correctly"""
    test_cases = [
        {
            "function": list_directories,
            "args": ("remote:path",),
            "expected_cmd": ["lsf", "remote:path", "--dirs-only"]
        },
        {
            "function": list_files,
            "args": ("remote:path", True),
            "expected_cmd": ["lsf", "remote:path", "-R"]
        }
    ]
    
    for case in test_cases:
        with patch('videostove_cli.rclone_io.run_rclone_command') as mock_cmd:
            mock_cmd.return_value = MagicMock(stdout="")
            
            case["function"](*case["args"])
            
            # Check the command arguments
            called_args = mock_cmd.call_args[0][0]
            assert called_args == case["expected_cmd"]