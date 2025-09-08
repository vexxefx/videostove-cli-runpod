"""
Tests for preset loading, parsing, and mode detection
"""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from videostove_cli.presets import (
    load_preset_file,
    extract_preset_profiles,
    load_preset_config,
    detect_mode,
    get_preset_summary,
    validate_preset_config,
    find_preset_files
)


def test_load_preset_file():
    """Test loading preset files"""
    with TemporaryDirectory() as tmpdir:
        preset_path = Path(tmpdir) / "test.json"
        
        # Valid JSON
        test_data = {"project_type": "slideshow"}
        preset_path.write_text(json.dumps(test_data))
        
        result = load_preset_file(preset_path)
        assert result == test_data
        
        # Invalid JSON
        preset_path.write_text("{invalid json")
        with pytest.raises(Exception):
            load_preset_file(preset_path)
        
        # Non-existent file
        with pytest.raises(Exception):
            load_preset_file(Path(tmpdir) / "missing.json")


def test_extract_preset_profiles():
    """Test extracting profiles from different preset formats"""
    
    # Format 1: Export format with "preset" wrapper
    export_format = {
        "metadata": {"version": "1.0"},
        "preset": {
            "profile1": {"project_type": "slideshow"},
            "profile2": {"project_type": "montage"}
        }
    }
    
    profiles = extract_preset_profiles(export_format)
    assert len(profiles) == 2
    assert "profile1" in profiles
    assert "profile2" in profiles
    assert profiles["profile1"]["project_type"] == "slideshow"
    
    # Format 2: Direct profile collection
    direct_format = {
        "slideshow_preset": {"project_type": "slideshow"},
        "montage_preset": {"project_type": "montage"},
        "metadata": "should be filtered out"
    }
    
    profiles = extract_preset_profiles(direct_format)
    assert len(profiles) == 2
    assert "slideshow_preset" in profiles
    assert "montage_preset" in profiles
    assert "metadata" not in profiles
    
    # Format 3: Single configuration
    single_format = {
        "project_type": "slideshow",
        "image_duration": 8.0,
        "use_crossfade": True
    }
    
    profiles = extract_preset_profiles(single_format)
    assert len(profiles) == 1
    assert "default" in profiles
    assert profiles["default"]["project_type"] == "slideshow"
    
    # Invalid format
    with pytest.raises(Exception):
        extract_preset_profiles({"invalid": "data"})


def test_load_preset_config():
    """Test loading specific preset configurations"""
    with TemporaryDirectory() as tmpdir:
        preset_path = Path(tmpdir) / "multi.json"
        
        # Multi-profile preset
        multi_data = {
            "preset": {
                "fast": {"project_type": "slideshow", "crf": 28},
                "quality": {"project_type": "montage", "crf": 18}
            }
        }
        preset_path.write_text(json.dumps(multi_data))
        
        # Load specific profile
        config = load_preset_config(preset_path, "fast")
        assert config["project_type"] == "slideshow"
        assert config["crf"] == 28
        
        config = load_preset_config(preset_path, "quality")
        assert config["project_type"] == "montage"
        assert config["crf"] == 18
        
        # Missing profile
        with pytest.raises(Exception):
            load_preset_config(preset_path, "missing")
        
        # Single profile preset
        single_path = Path(tmpdir) / "single.json"
        single_data = {"project_type": "slideshow"}
        single_path.write_text(json.dumps(single_data))
        
        config = load_preset_config(single_path)
        assert config["project_type"] == "slideshow"


def test_detect_mode():
    """Test mode detection from configurations"""
    
    # Direct project_type
    assert detect_mode({"project_type": "slideshow"}) == "slideshow"
    assert detect_mode({"project_type": "montage"}) == "montage"
    assert detect_mode({"project_type": "videos_only"}) == "videos_only"
    
    # Case insensitive
    assert detect_mode({"project_type": "SLIDESHOW"}) == "slideshow"
    assert detect_mode({"project_type": "Montage"}) == "montage"
    
    # Common variations
    assert detect_mode({"project_type": "slide"}) == "slideshow"
    assert detect_mode({"project_type": "photos"}) == "slideshow"
    assert detect_mode({"project_type": "video"}) == "montage"
    assert detect_mode({"project_type": "videos"}) == "videos_only"
    
    # Fallback to default
    assert detect_mode({}) == "montage"
    assert detect_mode({"project_type": "unknown"}) == "montage"


def test_get_preset_summary():
    """Test extracting preset summary for display"""
    config = {
        "project_type": "slideshow",
        "image_duration": 8.0,
        "use_crossfade": True,
        "use_overlay": False,
        "crf": 22,
        "use_gpu": True,
        "unknown_field": "should be ignored"
    }
    
    summary = get_preset_summary(config)
    
    assert "Mode" in summary
    assert summary["Mode"] == "slideshow"
    assert "Image Duration (s)" in summary
    assert summary["Image Duration (s)"] == 8.0
    assert "Crossfade" in summary
    assert summary["Crossfade"] == "Yes"
    assert "Overlay Enabled" in summary
    assert summary["Overlay Enabled"] == "No"
    assert "unknown_field" not in str(summary)


def test_validate_preset_config():
    """Test preset configuration validation"""
    
    # Valid config
    valid_config = {
        "project_type": "slideshow",
        "image_duration": 8.0,
        "crossfade_duration": 0.5,
        "crf": 22,
        "overlay_opacity": 0.7
    }
    
    issues = validate_preset_config(valid_config)
    assert len(issues) == 0
    
    # Missing required field
    invalid_config = {"image_duration": 8.0}
    issues = validate_preset_config(invalid_config)
    assert any("project_type" in issue for issue in issues)
    
    # Invalid numeric values
    invalid_numeric = {
        "project_type": "slideshow",
        "image_duration": -1.0,  # Too low
        "crf": 100,  # Too high
        "overlay_opacity": 2.0  # Too high
    }
    
    issues = validate_preset_config(invalid_numeric)
    assert len(issues) >= 3
    assert any("image_duration" in issue for issue in issues)
    assert any("crf" in issue for issue in issues)
    assert any("overlay_opacity" in issue for issue in issues)
    
    # Invalid choice values
    invalid_choice = {
        "project_type": "invalid_mode",
        "overlay_mode": "invalid_overlay",
        "preset": "invalid_preset"
    }
    
    issues = validate_preset_config(invalid_choice)
    assert len(issues) >= 3


def test_find_preset_files():
    """Test finding preset files in directories"""
    with TemporaryDirectory() as tmpdir:
        preset_dir = Path(tmpdir) / "presets"
        preset_dir.mkdir()
        
        # Create valid preset files
        valid1 = preset_dir / "slideshow.json"
        valid1.write_text(json.dumps({"project_type": "slideshow"}))
        
        valid2 = preset_dir / "multi.json"
        valid2.write_text(json.dumps({
            "preset": {
                "fast": {"project_type": "montage"},
                "slow": {"project_type": "slideshow"}
            }
        }))
        
        # Create invalid file
        invalid = preset_dir / "invalid.json"
        invalid.write_text("{invalid json}")
        
        # Create non-JSON file
        non_json = preset_dir / "readme.txt"
        non_json.write_text("not a preset")
        
        # Find presets
        found = find_preset_files([preset_dir])
        
        # Should find valid presets only
        found_names = [name for name, path in found]
        assert "slideshow" in found_names
        assert "multi:fast" in found_names
        assert "multi:slow" in found_names
        assert len([n for n in found_names if "invalid" in n]) == 0
        assert len([n for n in found_names if "readme" in n]) == 0
        
        # Test with non-existent directory
        found_empty = find_preset_files([Path(tmpdir) / "missing"])
        assert len(found_empty) == 0