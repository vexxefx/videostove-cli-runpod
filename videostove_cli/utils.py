"""
Utility functions for tables, prompts, and formatting
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


def format_table(headers: List[str], rows: List[List[Any]], max_width: int = 120) -> str:
    """
    Format data as a table with proper alignment
    
    Args:
        headers: Column headers
        rows: Data rows
        max_width: Maximum table width
        
    Returns:
        Formatted table string
    """
    if not rows:
        return "No data to display"
    
    # Calculate column widths
    col_widths = [len(header) for header in headers]
    
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Adjust widths if table is too wide
    total_width = sum(col_widths) + len(headers) * 3 - 1  # 3 chars per separator
    if total_width > max_width:
        # Proportionally reduce widths
        reduction = (total_width - max_width) / len(col_widths)
        col_widths = [max(8, int(w - reduction)) for w in col_widths]
    
    # Format table
    lines = []
    
    # Header
    header_line = " | ".join(header.ljust(col_widths[i]) for i, header in enumerate(headers))
    lines.append(header_line)
    
    # Separator
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    lines.append(sep_line)
    
    # Data rows
    for row in rows:
        row_line = " | ".join(
            str(cell).ljust(col_widths[i])[:col_widths[i]] 
            for i, cell in enumerate(row)
        )
        lines.append(row_line)
    
    return "\n".join(lines)


def numeric_choice_prompt(
    items: List[Tuple[str, Any]],
    prompt: str = "Select",
    allow_all: bool = False,
    allow_none: bool = False
) -> Union[List[Any], Any, None]:
    """
    Present a numeric choice menu and get user selection
    
    Args:
        items: List of (display_name, value) tuples
        prompt: Prompt text
        allow_all: Whether to allow selecting all items
        allow_none: Whether to allow selecting none
        
    Returns:
        Selected value(s) or None
    """
    if not items:
        print("No items available for selection")
        return None
    
    # Display options
    print(f"\n{prompt}:")
    for i, (display, _) in enumerate(items, 1):
        print(f"  {i}) {display}")
    
    if allow_all:
        print(f"  99) All ({len(items)} items)")
    
    if allow_none:
        print("  0) None")
    
    # Get input
    while True:
        try:
            choice = input(f"\nEnter choice: ").strip()
            
            if not choice:
                continue
            
            if choice == "0" and allow_none:
                return None
            
            if choice == "99" and allow_all:
                return [value for _, value in items]
            
            # Single numeric choice
            choice_num = int(choice)
            if 1 <= choice_num <= len(items):
                return items[choice_num - 1][1]  # Return value, not display name
            
            print(f"Invalid choice. Enter 1-{len(items)}" + 
                  (", 99 for all" if allow_all else "") +
                  (", 0 for none" if allow_none else ""))
                  
        except ValueError:
            print("Please enter a number")
        except KeyboardInterrupt:
            print("\nCancelled by user")
            return None


def multi_numeric_choice_prompt(
    items: List[Tuple[str, Any]],
    prompt: str = "Select",
    allow_all: bool = False
) -> List[Any]:
    """
    Present a numeric choice menu allowing multiple selections
    
    Args:
        items: List of (display_name, value) tuples
        prompt: Prompt text
        allow_all: Whether to allow selecting all items
        
    Returns:
        List of selected values
    """
    if not items:
        print("No items available for selection")
        return []
    
    # Display options
    print(f"\n{prompt} (comma-separated numbers):")
    for i, (display, _) in enumerate(items, 1):
        print(f"  {i}) {display}")
    
    if allow_all:
        print(f"  99) All ({len(items)} items)")
    
    # Get input
    while True:
        try:
            choice_str = input(f"\nEnter choices: ").strip()
            
            if not choice_str:
                continue
            
            if choice_str == "99" and allow_all:
                return [value for _, value in items]
            
            # Parse comma-separated choices
            choices = []
            for part in choice_str.split(','):
                choice_num = int(part.strip())
                if 1 <= choice_num <= len(items):
                    choices.append(items[choice_num - 1][1])
                else:
                    print(f"Invalid choice: {choice_num}")
                    break
            else:
                # All choices valid
                return choices
                
        except ValueError:
            print("Please enter comma-separated numbers")
        except KeyboardInterrupt:
            print("\nCancelled by user")
            return []


def confirm_prompt(message: str, default: bool = False) -> bool:
    """
    Ask for yes/no confirmation
    
    Args:
        message: Confirmation message
        default: Default value if user just presses enter
        
    Returns:
        True for yes, False for no
    """
    default_text = "Y/n" if default else "y/N"
    
    while True:
        try:
            response = input(f"{message} ({default_text}): ").strip().lower()
            
            if not response:
                return default
            
            if response in ('1', 'y', 'yes'):
                return True
            elif response in ('2', 'n', 'no'):
                return False
            else:
                print("Please enter 1/y/yes or 2/n/no")
                
        except KeyboardInterrupt:
            print("\nCancelled by user")
            return False


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable units"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024**2:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes/(1024**2):.1f} MB"
    else:
        return f"{size_bytes/(1024**3):.1f} GB"


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def truncate_path(path: Path, max_length: int = 40) -> str:
    """
    Truncate path for display while keeping filename
    
    Args:
        path: Path to truncate
        max_length: Maximum length
        
    Returns:
        Truncated path string
    """
    path_str = str(path)
    
    if len(path_str) <= max_length:
        return path_str
    
    # Try to keep filename and some parent context
    filename = path.name
    if len(filename) >= max_length - 3:
        return f"...{filename[-(max_length-3):]}"
    
    # Truncate middle part
    remaining = max_length - len(filename) - 3  # 3 for "..."
    if remaining > 0:
        parent = str(path.parent)
        if len(parent) > remaining:
            parent = parent[:remaining]
        return f"{parent}.../{filename}"
    
    return f".../{filename}"


def print_section(title: str, content: str = "") -> None:
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)
    if content:
        print(content)


def print_subsection(title: str) -> None:
    """Print a formatted subsection header"""
    print(f"\n--- {title} ---")


def format_project_plan_table(projects: List[Dict]) -> str:
    """
    Format project plan as a table
    
    Args:
        projects: List of project dicts with plan info
        
    Returns:
        Formatted table string
    """
    if not projects:
        return "No projects selected"
    
    headers = ["Project", "Mode", "Media", "Assets", "Output"]
    rows = []
    
    for project in projects:
        # Format media counts
        media = f"{project.get('images', 0)}i, {project.get('videos', 0)}v"
        
        # Format assets
        assets = []
        if project.get('overlay'):
            assets.append(f"O:{Path(project['overlay']).name}")
        if project.get('font'):
            assets.append(f"F:{Path(project['font']).name}")
        if project.get('bgm'):
            assets.append(f"M:{Path(project['bgm']).name}")
        
        asset_str = ", ".join(assets) if assets else "None"
        
        # Format output
        output_path = Path(project.get('output', ''))
        output_str = truncate_path(output_path, 25)
        
        rows.append([
            project['name'],
            project.get('mode', 'unknown'),
            media,
            asset_str,
            output_str
        ])
    
    return format_table(headers, rows)


def print_render_summary(projects: List[Dict], total_duration: float) -> None:
    """Print a summary of render results"""
    successful = [p for p in projects if p.get('success')]
    failed = [p for p in projects if not p.get('success')]
    
    print_section("Render Summary")
    
    print(f"✅ Successful: {len(successful)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"⏱️ Total Duration: {format_duration(total_duration)}")
    
    if successful:
        total_size = sum(p.get('output_size', 0) for p in successful)
        print(f"💾 Total Output Size: {format_file_size(total_size)}")
        
        print("\nSuccessful renders:")
        for project in successful:
            output_size = format_file_size(project.get('output_size', 0))
            duration = format_duration(project.get('duration', 0))
            print(f"  ✅ {project['name']} ({output_size}, {duration})")
    
    if failed:
        print("\nFailed renders:")
        for project in failed:
            error = project.get('error', 'Unknown error')
            print(f"  ❌ {project['name']}: {error}")