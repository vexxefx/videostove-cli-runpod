"""
Tests for media scanning and eligibility checking
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from videostove_cli.media_scan import (
    scan_project_media,
    select_main_audio,
    check_project_eligibility,
    scan_multiple_projects,
    find_asset_files,
    format_media_summary
)


def create_test_media_files(project_dir: Path):
    """Helper to create test media files"""
    # Create some images
    (project_dir / "image1.jpg").touch()
    (project_dir / "image2.png").touch()
    (project_dir / "subdir").mkdir()
    (project_dir / "subdir" / "image3.jpeg").touch()
    
    # Create some videos
    (project_dir / "video1.mp4").touch()
    (project_dir / "video2.mov").touch()
    
    # Create audio files
    (project_dir / "audio1.mp3").touch()
    (project_dir / "main_audio.wav").touch()
    (project_dir / "background.flac").touch()
    
    # Create files to skip
    (project_dir / "assets").mkdir()
    (project_dir / "assets" / "overlay.mp4").touch()
    (project_dir / "out").mkdir()
    (project_dir / "out" / "output.mp4").touch()


def test_scan_project_media():
    """Test scanning project directories for media"""
    with TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()
        
        create_test_media_files(project_dir)
        
        result = scan_project_media(project_dir)
        
        # Check counts
        assert len(result["images"]) == 3  # image1.jpg, image2.png, subdir/image3.jpeg
        assert len(result["videos"]) == 2  # video1.mp4, video2.mov
        assert len(result["audio"]) == 3   # audio1.mp3, main_audio.wav, background.flac
        
        # Check main audio selection (should prefer "main_audio.wav")
        assert result["main_audio"] is not None
        assert result["main_audio"].name == "main_audio.wav"
        
        # Check that assets and out directories were skipped
        assert not any("assets" in str(f) for f in result["images"])
        assert not any("out" in str(f) for f in result["videos"])
        
        # Check total size is calculated
        assert result["total_size"] >= 0
        
        # Test empty directory
        empty_dir = Path(tmpdir) / "empty"
        empty_dir.mkdir()
        
        empty_result = scan_project_media(empty_dir)
        assert len(empty_result["images"]) == 0
        assert len(empty_result["videos"]) == 0
        assert len(empty_result["audio"]) == 0
        assert empty_result["main_audio"] is None


def test_select_main_audio():
    """Test main audio file selection logic"""
    audio_files = [
        Path("background.mp3"),
        Path("main_track.wav"),
        Path("ambient.flac")
    ]
    
    # Should select file with "main" in name
    main_audio = select_main_audio(audio_files)
    assert main_audio.name == "main_track.wav"
    
    # Test without "main" in name (should select first)
    other_files = [
        Path("track1.mp3"),
        Path("track2.wav")
    ]
    
    main_audio = select_main_audio(other_files)
    assert main_audio.name == "track1.mp3"
    
    # Test empty list
    assert select_main_audio([]) is None


def test_check_project_eligibility():
    """Test project eligibility checking for different modes"""
    with TemporaryDirectory() as tmpdir:
        # Create projects for different scenarios
        
        # Slideshow project (images only)
        slideshow_dir = Path(tmpdir) / "slideshow"
        slideshow_dir.mkdir()
        (slideshow_dir / "image1.jpg").touch()
        (slideshow_dir / "image2.png").touch()
        
        result = check_project_eligibility(slideshow_dir, "slideshow")
        assert result["eligible"] == True
        assert "images" in result["reason"]
        assert result["media_counts"]["images"] == 2
        assert result["media_counts"]["videos"] == 0
        
        # Mixed project (images + videos) - not eligible for slideshow
        mixed_dir = Path(tmpdir) / "mixed"
        mixed_dir.mkdir()
        (mixed_dir / "image1.jpg").touch()
        (mixed_dir / "video1.mp4").touch()
        
        result = check_project_eligibility(mixed_dir, "slideshow")
        assert result["eligible"] == False
        assert "videos" in result["reason"].lower()
        
        # Mixed project - eligible for montage
        result = check_project_eligibility(mixed_dir, "montage")
        assert result["eligible"] == True
        assert result["media_counts"]["images"] == 1
        assert result["media_counts"]["videos"] == 1
        
        # Video-only project
        video_dir = Path(tmpdir) / "videos"
        video_dir.mkdir()
        (video_dir / "video1.mp4").touch()
        (video_dir / "video2.mov").touch()
        
        result = check_project_eligibility(video_dir, "videos_only")
        assert result["eligible"] == True
        assert result["media_counts"]["videos"] == 2
        
        # Empty project
        empty_dir = Path(tmpdir) / "empty"
        empty_dir.mkdir()
        
        result = check_project_eligibility(empty_dir, "slideshow")
        assert result["eligible"] == False
        assert "no images" in result["reason"].lower()


def test_scan_multiple_projects():
    """Test scanning multiple projects at once"""
    with TemporaryDirectory() as tmpdir:
        # Create different types of projects
        projects = []
        
        # Eligible slideshow project
        slideshow_dir = Path(tmpdir) / "slideshow"
        slideshow_dir.mkdir()
        (slideshow_dir / "image1.jpg").touch()
        (slideshow_dir / "image2.png").touch()
        projects.append(slideshow_dir)
        
        # Eligible montage project
        montage_dir = Path(tmpdir) / "montage"
        montage_dir.mkdir()
        (montage_dir / "image1.jpg").touch()
        (montage_dir / "video1.mp4").touch()
        projects.append(montage_dir)
        
        # Ineligible project (empty)
        empty_dir = Path(tmpdir) / "empty"
        empty_dir.mkdir()
        projects.append(empty_dir)
        
        # Scan for slideshow mode
        result = scan_multiple_projects(projects, "slideshow")
        
        assert len(result["eligible"]) == 1
        assert len(result["ineligible"]) == 2
        assert result["eligible"][0].name == "slideshow"
        
        # Check summary
        summary = result["summary"]
        assert summary["total_projects"] == 3
        assert summary["eligible_projects"] == 1
        assert summary["ineligible_projects"] == 2
        assert summary["mode"] == "slideshow"
        
        # Scan for montage mode
        result = scan_multiple_projects(projects, "montage")
        
        assert len(result["eligible"]) == 1  # Only montage project
        assert result["eligible"][0].name == "montage"


def test_find_asset_files():
    """Test finding asset files in directories"""
    with TemporaryDirectory() as tmpdir:
        # Create asset structure
        assets_dir = Path(tmpdir) / "assets"
        assets_dir.mkdir()
        
        # Create subdirectories with assets
        overlays_dir = assets_dir / "overlays"
        overlays_dir.mkdir()
        (overlays_dir / "overlay1.mp4").touch()
        (overlays_dir / "overlay2.mov").touch()
        
        fonts_dir = assets_dir / "fonts"
        fonts_dir.mkdir()
        (fonts_dir / "font1.ttf").touch()
        (fonts_dir / "font2.otf").touch()
        
        bgmusic_dir = assets_dir / "bgmusic"
        bgmusic_dir.mkdir()
        (bgmusic_dir / "music1.mp3").touch()
        (bgmusic_dir / "music2.wav").touch()
        
        # Create direct assets in root
        (assets_dir / "direct_overlay.mp4").touch()
        (assets_dir / "direct_font.ttf").touch()
        (assets_dir / "direct_music.mp3").touch()
        
        # Find assets
        result = find_asset_files([assets_dir])
        
        assert len(result["overlays"]) == 3  # 2 in subdir + 1 direct
        assert len(result["fonts"]) == 3     # 2 in subdir + 1 direct
        assert len(result["bgmusic"]) == 3   # 2 in subdir + 1 direct
        
        # Check that files are found
        overlay_names = [f.name for f in result["overlays"]]
        assert "overlay1.mp4" in overlay_names
        assert "direct_overlay.mp4" in overlay_names
        
        # Test with non-existent directory
        result_empty = find_asset_files([Path(tmpdir) / "missing"])
        assert len(result_empty["overlays"]) == 0
        assert len(result_empty["fonts"]) == 0
        assert len(result_empty["bgmusic"]) == 0


def test_format_media_summary():
    """Test formatting media summary for display"""
    media_info = {
        "images": [Path("img1.jpg"), Path("img2.png")],
        "videos": [Path("vid1.mp4")],
        "audio": [Path("aud1.mp3"), Path("aud2.wav")],
        "main_audio": Path("main.mp3"),
        "total_size": 1024 * 1024 * 50  # 50 MB
    }
    
    summary = format_media_summary(media_info, "test_project")
    
    assert "test_project" in summary
    assert "Images: 2" in summary
    assert "Videos: 1" in summary
    assert "Audio: 2" in summary
    assert "Main Audio: main.mp3" in summary
    assert "50.0 MB" in summary
    
    # Test without project name
    summary_no_name = format_media_summary(media_info)
    assert "test_project" not in summary_no_name
    assert "Images: 2" in summary_no_name
    
    # Test large size formatting (GB)
    large_media = media_info.copy()
    large_media["total_size"] = 1024 * 1024 * 1024 * 2  # 2 GB
    
    summary_large = format_media_summary(large_media)
    assert "2.0 GB" in summary_large