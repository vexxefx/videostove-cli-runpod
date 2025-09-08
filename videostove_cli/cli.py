"""
Main CLI interface with numeric wizards for VideoStove
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import DEFAULT_ROOT, RENDER_MODES
from .media_scan import (
    find_asset_files,
    scan_multiple_projects,
    check_project_eligibility
)
from .presets import (
    find_preset_files,
    load_preset_config,
    detect_mode,
    get_preset_summary,
    validate_preset_config
)
from .render import render_project, doctor_gpu
from .rclone_setup import (
    materialize_config_from_env,
    verify_remote,
    list_projects,
    pull_shared,
    pull_project,
    push_outputs,
    doctor_rclone
)
from .utils import (
    numeric_choice_prompt,
    multi_numeric_choice_prompt,
    confirm_prompt,
    format_project_plan_table,
    print_section,
    print_subsection,
    print_render_summary,
    format_duration
)
from .version import __version__


def cmd_wizard(args) -> int:
    """
    Main wizard command - preset-first, mode-aware, GPU-enforced
    """
    print_section("VideoStove CLI Wizard", f"Version {__version__}")
    
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Working directory: {root}")
    
    try:
        # Step 1: Pull shared assets if remote specified
        if args.remote:
            print_subsection("Remote Setup")
            print(f"🌐 Remote: {args.remote}")
            
            if not verify_remote(args.remote):
                print("❌ Remote verification failed")
                return 1
            
            print("✅ Remote verified")
            
            # Pull shared assets
            try:
                if pull_shared(args.remote, root):
                    print("📦 Shared assets pulled")
                else:
                    print("📦 No shared assets found")
            except Exception as e:
                print(f"⚠️ Failed to pull shared assets: {e}")
        
        # Step 2: Find and select preset
        print_subsection("Preset Selection")
        
        if args.preset:
            # Use specified preset
            if args.preset.startswith('/') or Path(args.preset).is_absolute():
                preset_path = Path(args.preset)
            else:
                # Look for preset in search paths
                search_paths = [root / "assets" / "presets"]
                if (root / "assets").exists():
                    search_paths.append(root / "assets")
                
                preset_found = False
                for search_path in search_paths:
                    candidate = search_path / args.preset
                    if candidate.exists():
                        preset_path = candidate
                        preset_found = True
                        break
                    
                    # Try with .json extension
                    candidate_json = search_path / f"{args.preset}.json"
                    if candidate_json.exists():
                        preset_path = candidate_json
                        preset_found = True
                        break
                
                if not preset_found:
                    print(f"❌ Preset not found: {args.preset}")
                    return 1
            
            print(f"📋 Using preset: {preset_path.name}")
            
        else:
            # Interactive preset selection
            search_paths = []
            if (root / "assets" / "presets").exists():
                search_paths.append(root / "assets" / "presets")
            if (root / "assets").exists():
                search_paths.append(root / "assets")
            
            available_presets = find_preset_files(search_paths)
            
            if not available_presets:
                print("❌ No presets found")
                if not search_paths:
                    print("   Try pulling shared assets first or specify --preset")
                return 1
            
            print(f"Found {len(available_presets)} presets:")
            
            if args.yes:
                # Use first preset in non-interactive mode
                preset_name, preset_path = available_presets[0]
            else:
                selected = numeric_choice_prompt(available_presets, "Choose preset")
                if selected is None:
                    return 1
                preset_path = selected
        
        # Load preset configuration
        try:
            # Handle profile selection for multi-profile presets
            profile_name = None
            if ':' in str(preset_path) and not Path(str(preset_path)).exists():
                # Handle "filename:profile" format
                parts = str(preset_path).split(':', 1)
                preset_path = Path(parts[0])
                profile_name = parts[1]
            
            preset_config = load_preset_config(preset_path, profile_name)
            
            # Validate preset
            issues = validate_preset_config(preset_config)
            if issues:
                print("⚠️ Preset validation issues:")
                for issue in issues:
                    print(f"   - {issue}")
                if not args.yes and not confirm_prompt("Continue anyway?"):
                    return 1
                    
        except Exception as e:
            print(f"❌ Failed to load preset: {e}")
            return 1
        
        # Step 3: Detect and optionally override mode
        detected_mode = detect_mode(preset_config)
        
        if args.mode:
            if args.mode not in RENDER_MODES:
                print(f"❌ Invalid mode: {args.mode}. Use: {', '.join(RENDER_MODES)}")
                return 1
            mode = args.mode
            print(f"🎯 Mode override: {mode} (detected: {detected_mode})")
        else:
            mode = detected_mode
            print(f"🎯 Detected mode: {mode}")
        
        # Show preset summary if requested
        if args.show_read:
            print_subsection("Preset Configuration")
            summary = get_preset_summary(preset_config)
            for key, value in summary.items():
                print(f"   {key}: {value}")
        
        # Step 4: List and select projects
        print_subsection("Project Selection")
        
        if args.remote:
            # List remote projects
            try:
                remote_projects = list_projects(args.remote)
                print(f"Found {len(remote_projects)} remote projects")
            except Exception as e:
                print(f"❌ Failed to list remote projects: {e}")
                return 1
            
            if not remote_projects:
                print("❌ No projects found in remote")
                return 1
            
            # Select projects to pull
            if args.select:
                if args.select == "all":
                    selected_project_names = remote_projects
                else:
                    # Parse comma-separated list
                    selected_project_names = [name.strip() for name in args.select.split(',')]
                    
                    # Verify all specified projects exist
                    invalid = [name for name in selected_project_names if name not in remote_projects]
                    if invalid:
                        print(f"❌ Projects not found: {', '.join(invalid)}")
                        return 1
                        
                print(f"📋 Selected {len(selected_project_names)} projects")
                
            else:
                # Interactive selection
                project_items = [(name, name) for name in remote_projects]
                
                if args.yes:
                    # Select all in non-interactive mode
                    selected_project_names = remote_projects
                else:
                    selected_project_names = multi_numeric_choice_prompt(
                        project_items, "Select projects to process", allow_all=True
                    )
                    
                    if not selected_project_names:
                        print("❌ No projects selected")
                        return 1
            
            # Pull selected projects
            print(f"📥 Pulling {len(selected_project_names)} projects...")
            pulled_projects = []
            
            for project_name in selected_project_names:
                try:
                    project_path = pull_project(args.remote, root, project_name)
                    pulled_projects.append(project_path)
                    print(f"   ✅ {project_name}")
                except Exception as e:
                    print(f"   ❌ {project_name}: {e}")
            
            project_paths = pulled_projects
            
        else:
            # Scan local projects
            project_paths = [p for p in root.iterdir() if p.is_dir() and p.name not in {"assets", "outputs"}]
            
            if not project_paths:
                print("❌ No local projects found")
                print("   Specify --remote to pull projects, or place projects in the working directory")
                return 1
            
            print(f"Found {len(project_paths)} local projects")
        
        # Step 5: Scan projects and filter by eligibility
        print_subsection("Project Analysis")
        
        scan_result = scan_multiple_projects(project_paths, mode)
        eligible_projects = scan_result["eligible"]
        ineligible_projects = scan_result["ineligible"]
        
        print(f"📊 Scan Summary:")
        print(f"   Total projects: {scan_result['summary']['total_projects']}")
        print(f"   Eligible for {mode}: {len(eligible_projects)}")
        print(f"   Ineligible: {len(ineligible_projects)}")
        print(f"   Total media: {scan_result['summary']['total_images']} images, {scan_result['summary']['total_videos']} videos")
        
        if ineligible_projects:
            print(f"\n❌ Ineligible projects:")
            for project_path, reason in ineligible_projects:
                print(f"   {project_path.name}: {reason}")
        
        if not eligible_projects:
            print("❌ No eligible projects found")
            return 1
        
        print(f"\n✅ Eligible projects:")
        for project_path in eligible_projects:
            result = check_project_eligibility(project_path, mode)
            print(f"   {project_path.name}: {result['reason']}")
        
        # Step 6: Asset selection
        print_subsection("Asset Selection")
        
        # Find available assets
        asset_search_paths = []
        if (root / "assets").exists():
            asset_search_paths.append(root / "assets")
        
        # Add project-specific asset directories
        for project_path in eligible_projects:
            project_assets = project_path / "assets"
            if project_assets.exists():
                asset_search_paths.append(project_assets)
        
        available_assets = find_asset_files(asset_search_paths)
        
        # Select assets
        selected_overlay = None
        selected_font = None
        selected_bgm = None
        
        # Overlay selection
        if args.overlay:
            selected_overlay = Path(args.overlay)
            print(f"🎭 Using overlay: {selected_overlay.name}")
        elif available_assets["overlays"] and not args.yes:
            overlay_items = [(f.name, f) for f in available_assets["overlays"]]
            selected_overlay = numeric_choice_prompt(overlay_items, "Select overlay", allow_none=True)
            if selected_overlay:
                print(f"🎭 Selected overlay: {selected_overlay.name}")
        
        # Font selection  
        if args.font:
            selected_font = Path(args.font)
            print(f"🔤 Using font: {selected_font.name}")
        elif available_assets["fonts"] and not args.yes:
            font_items = [(f.name, f) for f in available_assets["fonts"]]
            selected_font = numeric_choice_prompt(font_items, "Select font", allow_none=True)
            if selected_font:
                print(f"🔤 Selected font: {selected_font.name}")
        
        # Background music selection
        if args.bgm:
            selected_bgm = Path(args.bgm)
            print(f"🎵 Using background music: {selected_bgm.name}")
        elif available_assets["bgmusic"] and not args.yes:
            bgm_items = [(f.name, f) for f in available_assets["bgmusic"]]
            selected_bgm = numeric_choice_prompt(bgm_items, "Select background music", allow_none=True)
            if selected_bgm:
                print(f"🎵 Selected background music: {selected_bgm.name}")
        
        # Step 7: Create execution plan
        print_subsection("Execution Plan")
        
        projects_plan = []
        for project_path in eligible_projects:
            out_dir = project_path / "out"
            out_file = out_dir / f"{project_path.name}_{mode}.mp4"
            
            result = check_project_eligibility(project_path, mode)
            
            project_info = {
                "name": project_path.name,
                "path": project_path,
                "mode": mode,
                "images": result["media_counts"]["images"],
                "videos": result["media_counts"]["videos"],
                "overlay": str(selected_overlay) if selected_overlay else None,
                "font": str(selected_font) if selected_font else None,
                "bgm": str(selected_bgm) if selected_bgm else None,
                "output": str(out_file),
            }
            projects_plan.append(project_info)
        
        # Show plan table
        plan_table = format_project_plan_table(projects_plan)
        print(plan_table)
        
        # Confirmation
        if not args.yes:
            print(f"\n🎬 Ready to render {len(projects_plan)} projects")
            if not confirm_prompt("Proceed with rendering?", default=True):
                print("❌ Cancelled by user")
                return 1
        
        # Step 8: Execute renders
        print_section("Rendering")
        
        start_time = datetime.now()
        render_results = []
        
        for i, project_info in enumerate(projects_plan, 1):
            print(f"\n🎬 Rendering {i}/{len(projects_plan)}: {project_info['name']}")
            
            project_start = datetime.now()
            
            try:
                success = render_project(
                    project_dir=project_info["path"],
                    out_path=Path(project_info["output"]),
                    preset_config=preset_config,
                    mode=mode,
                    overlay=Path(project_info["overlay"]) if project_info["overlay"] else None,
                    font=Path(project_info["font"]) if project_info["font"] else None,
                    bgm=Path(project_info["bgm"]) if project_info["bgm"] else None,
                    show_read=args.show_read
                )
                
                project_end = datetime.now()
                project_duration = (project_end - project_start).total_seconds()
                
                if success:
                    output_path = Path(project_info["output"])
                    output_size = output_path.stat().st_size if output_path.exists() else 0
                    
                    render_results.append({
                        "name": project_info["name"],
                        "success": True,
                        "duration": project_duration,
                        "output_size": output_size,
                        "output_path": output_path,
                    })
                    
                else:
                    render_results.append({
                        "name": project_info["name"],
                        "success": False,
                        "duration": project_duration,
                        "error": "Render failed",
                    })
                    
            except Exception as e:
                project_end = datetime.now()
                project_duration = (project_end - project_start).total_seconds()
                
                render_results.append({
                    "name": project_info["name"],
                    "success": False,
                    "duration": project_duration,
                    "error": str(e),
                })
                
                print(f"❌ Render failed: {e}")
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        # Step 9: Push outputs if requested
        if args.remote and (args.push or (args.push is None and not args.no_push)):
            successful_results = [r for r in render_results if r["success"]]
            
            if successful_results:
                push_decision = args.push
                if push_decision is None and not args.yes:
                    push_decision = confirm_prompt(
                        f"Push {len(successful_results)} outputs to remote?", 
                        default=True
                    )
                
                if push_decision:
                    print_subsection("Pushing Outputs")
                    
                    for result in successful_results:
                        project_name = result["name"]
                        project_path = next(p for p in eligible_projects if p.name == project_name)
                        
                        try:
                            if push_outputs(args.remote, project_path):
                                print(f"   ✅ {project_name}")
                            else:
                                print(f"   ⚠️ {project_name}: No outputs to push")
                        except Exception as e:
                            print(f"   ❌ {project_name}: {e}")
        
        # Step 10: Summary
        print_render_summary(render_results, total_duration)
        
        successful_count = len([r for r in render_results if r["success"]])
        failed_count = len(render_results) - successful_count
        
        if failed_count == 0:
            print("🎉 All renders completed successfully!")
            return 0
        elif successful_count > 0:
            print("⚠️ Some renders failed")
            return 2
        else:
            print("❌ All renders failed")
            return 1
            
    except KeyboardInterrupt:
        print("\n❌ Cancelled by user")
        return 130
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1


def cmd_pull(args) -> int:
    """Pull projects and/or shared assets from remote"""
    if not args.remote:
        print("❌ --remote is required for pull command")
        return 1
    
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    
    try:
        if not verify_remote(args.remote):
            print("❌ Remote verification failed")
            return 1
        
        if args.shared_only:
            # Pull only shared assets
            if pull_shared(args.remote, root):
                print("✅ Shared assets pulled")
            else:
                print("⚠️ No shared assets found")
            return 0
        
        # Pull projects
        if args.projects:
            if args.projects == "all":
                project_names = list_projects(args.remote)
            else:
                project_names = [name.strip() for name in args.projects.split(',')]
        else:
            # Interactive selection
            available_projects = list_projects(args.remote)
            if not available_projects:
                print("❌ No projects found")
                return 1
            
            project_items = [(name, name) for name in available_projects]
            project_names = multi_numeric_choice_prompt(
                project_items, "Select projects to pull", allow_all=True
            )
            
            if not project_names:
                return 1
        
        # Pull selected projects
        for project_name in project_names:
            try:
                pull_project(args.remote, root, project_name)
                print(f"✅ {project_name}")
            except Exception as e:
                print(f"❌ {project_name}: {e}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Pull failed: {e}")
        return 1


def cmd_push(args) -> int:
    """Push project outputs to remote"""
    if not args.remote:
        print("❌ --remote is required for push command")
        return 1
    
    root = Path(args.root).resolve()
    
    try:
        if not verify_remote(args.remote):
            print("❌ Remote verification failed")
            return 1
        
        # Find projects
        if args.projects:
            if args.projects == "all":
                project_paths = [p for p in root.iterdir() if p.is_dir() and p.name not in {"assets", "outputs"}]
            else:
                project_names = [name.strip() for name in args.projects.split(',')]
                project_paths = []
                for name in project_names:
                    project_path = root / name
                    if project_path.exists():
                        project_paths.append(project_path)
                    else:
                        print(f"⚠️ Project not found: {name}")
        else:
            # Interactive selection
            available_projects = [p for p in root.iterdir() if p.is_dir() and p.name not in {"assets", "outputs"}]
            if not available_projects:
                print("❌ No projects found")
                return 1
            
            project_items = [(p.name, p) for p in available_projects]
            project_paths = multi_numeric_choice_prompt(
                project_items, "Select projects to push outputs", allow_all=True
            )
            
            if not project_paths:
                return 1
        
        # Push outputs
        for project_path in project_paths:
            try:
                if push_outputs(args.remote, project_path):
                    print(f"✅ {project_path.name}")
                else:
                    print(f"⚠️ {project_path.name}: No outputs to push")
            except Exception as e:
                print(f"❌ {project_path.name}: {e}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Push failed: {e}")
        return 1


def cmd_scan(args) -> int:
    """Scan local projects for media"""
    root = Path(args.root).resolve()
    
    if not root.exists():
        print(f"❌ Root directory not found: {root}")
        return 1
    
    project_paths = [p for p in root.iterdir() if p.is_dir() and p.name not in {"assets", "outputs"}]
    
    if not project_paths:
        print("❌ No projects found")
        return 1
    
    if args.json:
        import json
        
        result = {}
        for project_path in project_paths:
            from .media_scan import scan_project_media
            media_info = scan_project_media(project_path)
            
            result[project_path.name] = {
                "images": len(media_info["images"]),
                "videos": len(media_info["videos"]),
                "audio": len(media_info["audio"]),
                "total_size_bytes": media_info["total_size"],
                "main_audio": str(media_info["main_audio"]) if media_info["main_audio"] else None,
                "inferred_mode": "montage" if len(media_info["videos"]) > 0 else "slideshow"
            }
        
        print(json.dumps(result, indent=2))
        
    else:
        print(f"Found {len(project_paths)} projects:\n")
        
        for project_path in project_paths:
            from .media_scan import scan_project_media, format_media_summary
            media_info = scan_project_media(project_path)
            
            print(format_media_summary(media_info, project_path.name))
            
            # Show inferred mode
            inferred_mode = "montage" if len(media_info["videos"]) > 0 else "slideshow"
            print(f"🎯 Inferred mode: {inferred_mode}\n")
    
    return 0


def cmd_doctor(args) -> int:
    """Check system requirements and configuration"""
    print_section("VideoStove Doctor")
    
    all_good = True
    
    # Check Python
    print_subsection("Python Environment")
    print(f"✅ Python: {sys.version}")
    
    # Check GPU
    print_subsection("GPU Configuration")
    gpu_info = doctor_gpu()
    
    if gpu_info["nvidia_smi_available"]:
        print("✅ nvidia-smi available")
        for gpu in gpu_info["nvidia_gpus"]:
            print(f"   {gpu}")
    else:
        print("❌ nvidia-smi not available")
        all_good = False
    
    if gpu_info["torch_available"]:
        print("✅ PyTorch available")
        if gpu_info["torch_cuda_available"]:
            print(f"✅ PyTorch CUDA available ({gpu_info['cuda_device_count']} devices)")
        else:
            print("❌ PyTorch CUDA not available")
            all_good = False
    else:
        print("❌ PyTorch not available")
        all_good = False
    
    if gpu_info["allow_cpu_set"]:
        print("⚠️ ALLOW_CPU=1 is set (debug mode)")
    
    # Check rclone
    print_subsection("rclone Configuration")
    rclone_info = doctor_rclone()
    
    if rclone_info["rclone_available"]:
        print(f"✅ rclone available (v{rclone_info['rclone_version']})")
    else:
        print("❌ rclone not available")
        all_good = False
    
    if rclone_info["config_exists"]:
        print(f"✅ rclone config exists: {rclone_info['config_path']}")
        if rclone_info["remotes_configured"]:
            print(f"   Configured remotes: {', '.join(rclone_info['remotes_configured'])}")
        else:
            print("   No remotes configured")
    else:
        print(f"⚠️ No rclone config found: {rclone_info['config_path']}")
        print("   Set RCLONE_CONFIG_BASE64 or RCLONE_DRIVE_SERVICE_ACCOUNT_JSON")
    
    # Check videostove engine
    print_subsection("VideoStove Engine")
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import run_main as vs
        print("✅ VideoStove engine available")
        
        if hasattr(vs, 'CONFIG'):
            print("✅ CONFIG object found")
        else:
            print("⚠️ CONFIG object not found")
            
    except ImportError as e:
        print(f"❌ VideoStove engine not available: {e}")
        print("   Ensure run_main.py is in the parent directory")
        all_good = False
    
    # Summary
    print_section("Summary")
    if all_good:
        print("✅ All checks passed! Ready for rendering.")
        return 0
    else:
        print("❌ Some checks failed. Please resolve the issues above.")
        return 1


def cmd_rclone_setup(args) -> int:
    """Setup rclone configuration headlessly"""
    print_section("rclone Setup")
    
    try:
        if materialize_config_from_env():
            print("✅ rclone configuration created successfully")
            
            # Test configuration
            print("🔍 Testing configuration...")
            rclone_info = doctor_rclone()
            
            if rclone_info["remotes_configured"]:
                print(f"✅ Found remotes: {', '.join(rclone_info['remotes_configured'])}")
            else:
                print("⚠️ No remotes configured")
                
            return 0
        else:
            print("⚠️ No configuration environment variables found")
            print("   Set one of:")
            print("   - RCLONE_CONFIG_BASE64")
            print("   - RCLONE_DRIVE_SERVICE_ACCOUNT_JSON + RCLONE_REMOTE_NAME")
            return 1
            
    except Exception as e:
        print(f"❌ rclone setup failed: {e}")
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser"""
    parser = argparse.ArgumentParser(
        prog="videostove",
        description="VideoStove CLI - GPU-first video rendering for RunPod",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive wizard
  videostove wizard --root /workspace/videostove_root --remote gdrive:VideoStove

  # Non-interactive batch processing
  videostove wizard --root /workspace/videostove_root --remote gdrive:VideoStove \\
                    --preset twovet.json --select all --yes --push

  # Check system status
  videostove doctor

  # Pull specific projects
  videostove pull --remote gdrive:VideoStove --projects "project1,project2"
        """
    )
    
    parser.add_argument("--version", action="version", version=f"videostove {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Wizard command (main)
    wizard_parser = subparsers.add_parser("wizard", help="Main rendering wizard")
    wizard_parser.add_argument("--root", type=str, default=str(DEFAULT_ROOT),
                              help="Working directory (default: %(default)s)")
    wizard_parser.add_argument("--remote", type=str,
                              help="rclone remote path (e.g., gdrive:VideoStove)")
    wizard_parser.add_argument("--preset", type=str,
                              help="Preset name or path")
    wizard_parser.add_argument("--select", type=str,
                              help="Select projects: 'all' or comma-separated names")
    wizard_parser.add_argument("--mode", choices=RENDER_MODES,
                              help="Override preset mode")
    wizard_parser.add_argument("--overlay", type=str,
                              help="Overlay video file path")
    wizard_parser.add_argument("--font", type=str,
                              help="Font file path")
    wizard_parser.add_argument("--bgm", type=str,
                              help="Background music file path")
    wizard_parser.add_argument("--show-read", action="store_true",
                              help="Show detailed readouts")
    wizard_parser.add_argument("--yes", action="store_true",
                              help="Auto-confirm all prompts")
    
    push_group = wizard_parser.add_mutually_exclusive_group()
    push_group.add_argument("--push", action="store_true",
                           help="Push outputs to remote after rendering")
    push_group.add_argument("--no-push", action="store_true",
                           help="Don't push outputs to remote")
    
    # Pull command
    pull_parser = subparsers.add_parser("pull", help="Pull projects/assets from remote")
    pull_parser.add_argument("--root", type=str, default=str(DEFAULT_ROOT),
                            help="Working directory")
    pull_parser.add_argument("--remote", type=str, required=True,
                            help="rclone remote path")
    pull_parser.add_argument("--projects", type=str,
                            help="Projects to pull: 'all' or comma-separated names")
    pull_parser.add_argument("--shared-only", action="store_true",
                            help="Pull only shared assets")
    
    # Push command
    push_parser = subparsers.add_parser("push", help="Push outputs to remote")
    push_parser.add_argument("--root", type=str, default=str(DEFAULT_ROOT),
                            help="Working directory")
    push_parser.add_argument("--remote", type=str, required=True,
                            help="rclone remote path")
    push_parser.add_argument("--projects", type=str,
                            help="Projects to push: 'all' or comma-separated names")
    
    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan local projects")
    scan_parser.add_argument("--root", type=str, default=str(DEFAULT_ROOT),
                            help="Working directory")
    scan_parser.add_argument("--json", action="store_true",
                            help="Output as JSON")
    
    # Doctor command
    subparsers.add_parser("doctor", help="Check system requirements")
    
    # rclone setup command
    subparsers.add_parser("rclone-setup", help="Setup rclone configuration")
    
    return parser


def main() -> int:
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        # Default to wizard if no command specified
        args.command = "wizard"
        args.root = str(DEFAULT_ROOT)
        args.remote = os.environ.get("REMOTE_BASE")
        args.preset = None
        args.select = None
        args.mode = None
        args.overlay = None
        args.font = None
        args.bgm = None
        args.show_read = False
        args.yes = False
        args.push = None
        args.no_push = False
    
    # Route to command handlers
    command_handlers = {
        "wizard": cmd_wizard,
        "pull": cmd_pull,
        "push": cmd_push,
        "scan": cmd_scan,
        "doctor": cmd_doctor,
        "rclone-setup": cmd_rclone_setup,
    }
    
    handler = command_handlers.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"❌ Unknown command: {args.command}")
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())