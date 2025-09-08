"""
Tests for CLI planning and table formatting
"""

import pytest
from pathlib import Path

from videostove_cli.utils import (
    format_table,
    numeric_choice_prompt,
    multi_numeric_choice_prompt,
    confirm_prompt,
    format_project_plan_table,
    format_file_size,
    format_duration,
    truncate_path
)


def test_format_table():
    """Test table formatting"""
    headers = ["Name", "Type", "Size"]
    rows = [
        ["project1", "slideshow", "10MB"],
        ["project2", "montage", "25MB"],
        ["very_long_project_name", "videos_only", "100MB"]
    ]
    
    table = format_table(headers, rows)
    
    # Check that headers are present
    assert "Name" in table
    assert "Type" in table
    assert "Size" in table
    
    # Check that data is present
    assert "project1" in table
    assert "slideshow" in table
    assert "10MB" in table
    
    # Check that separators are present
    assert "-+-" in table or "---" in table
    
    # Test empty rows
    empty_table = format_table(headers, [])
    assert "No data to display" in empty_table


def test_format_project_plan_table():
    """Test project plan table formatting"""
    projects = [
        {
            "name": "project1",
            "mode": "slideshow",
            "images": 10,
            "videos": 0,
            "overlay": "/path/to/overlay.mp4",
            "font": "/path/to/font.ttf", 
            "bgm": "/path/to/music.mp3",
            "output": "/workspace/project1/out/project1_slideshow.mp4"
        },
        {
            "name": "project2",
            "mode": "montage",
            "images": 5,
            "videos": 3,
            "overlay": None,
            "font": None,
            "bgm": "/path/to/bg.wav",
            "output": "/workspace/project2/out/project2_montage.mp4"
        }
    ]
    
    table = format_project_plan_table(projects)
    
    # Check headers
    assert "Project" in table
    assert "Mode" in table
    assert "Media" in table
    assert "Assets" in table
    assert "Output" in table
    
    # Check data
    assert "project1" in table
    assert "slideshow" in table
    assert "10i, 0v" in table  # Media format
    assert "O:overlay.mp4" in table  # Overlay asset
    assert "F:font.ttf" in table     # Font asset
    assert "M:music.mp3" in table    # Music asset
    
    assert "project2" in table
    assert "montage" in table
    assert "5i, 3v" in table
    assert "M:bg.wav" in table
    
    # Test empty projects
    empty_table = format_project_plan_table([])
    assert "No projects selected" in empty_table


def test_format_file_size():
    """Test file size formatting"""
    assert format_file_size(512) == "512 B"
    assert format_file_size(1024) == "1.0 KB"
    assert format_file_size(1024 * 1024) == "1.0 MB"
    assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"
    assert format_file_size(1536) == "1.5 KB"  # 1.5 KB
    assert format_file_size(2.5 * 1024 * 1024) == "2.5 MB"


def test_format_duration():
    """Test duration formatting"""
    assert format_duration(30) == "30.0s"
    assert format_duration(90) == "1.5m"
    assert format_duration(3600) == "1.0h"
    assert format_duration(3660) == "1.0h"  # 1 hour 1 minute
    assert format_duration(0.5) == "0.5s"


def test_truncate_path():
    """Test path truncation"""
    # Short path - no truncation
    short_path = Path("project1/file.mp4")
    assert truncate_path(short_path, 50) == str(short_path)
    
    # Long path - should truncate middle
    long_path = Path("very/long/path/structure/with/many/directories/final_file.mp4")
    truncated = truncate_path(long_path, 30)
    
    assert len(truncated) <= 30
    assert truncated.startswith("very/long/path")  # Keeps beginning
    assert truncated.endswith("final_file.mp4")   # Keeps filename
    assert "..." in truncated                     # Has ellipsis
    
    # Very long filename
    very_long_file = Path("very_very_very_long_filename_that_exceeds_limit.mp4")
    truncated = truncate_path(very_long_file, 20)
    
    assert len(truncated) <= 20
    assert truncated.startswith("...")
    assert truncated.endswith(".mp4")


# Note: Interactive prompt tests would require input mocking
# These are integration tests that are harder to test without actual user input
# In a real test suite, you might use pytest fixtures or mock input


def test_table_column_widths():
    """Test that table columns are properly sized"""
    headers = ["Short", "Very Long Header Name", "Med"]
    rows = [
        ["A", "Short content", "Medium"],
        ["Longer text", "B", "X"]
    ]
    
    table = format_table(headers, rows)
    lines = table.split('\n')
    
    # All lines should have similar length (accounting for content variations)
    line_lengths = [len(line) for line in lines if line.strip()]
    max_len = max(line_lengths)
    min_len = min(line_lengths)
    
    # Lines should be roughly the same length (within reason)
    assert max_len - min_len <= 5  # Allow some variation for content


def test_table_with_max_width():
    """Test table respects maximum width constraint"""
    headers = ["Very Long Header 1", "Very Long Header 2", "Very Long Header 3"]
    rows = [
        ["Very long content that might exceed limits", 
         "More very long content here", 
         "And even more long content"]
    ]
    
    max_width = 50
    table = format_table(headers, rows, max_width=max_width)
    lines = table.split('\n')
    
    # Check that no line exceeds max width significantly
    for line in lines:
        # Allow small overrun due to formatting
        assert len(line) <= max_width + 10


def test_asset_formatting_in_plan():
    """Test how assets are formatted in project plan"""
    project_with_all_assets = {
        "name": "test",
        "mode": "slideshow", 
        "images": 1,
        "videos": 0,
        "overlay": "/very/long/path/to/overlay_file.mp4",
        "font": "/path/font.ttf",
        "bgm": "/path/music.mp3",
        "output": "/out.mp4"
    }
    
    project_no_assets = {
        "name": "test2",
        "mode": "montage",
        "images": 1,
        "videos": 1, 
        "overlay": None,
        "font": None,
        "bgm": None,
        "output": "/out2.mp4"
    }
    
    table = format_project_plan_table([project_with_all_assets, project_no_assets])
    
    # Check asset abbreviations
    assert "O:" in table  # Overlay
    assert "F:" in table  # Font  
    assert "M:" in table  # Music
    
    # Check "None" for project without assets
    assert "None" in table