#!/usr/bin/env python3

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from datetime import datetime, timedelta
import logging

app = FastAPI()

# Allow GitHub to fetch the SVG
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://github.com", "https://raw.githubusercontent.com"],
    allow_methods=["GET"],
)

DB_PATH = "/var/lib/gpu-brrrometer/activity.db"

def get_activity_data(weeks=53):
    """Fetch activity data for the specified number of weeks."""
    end_date = datetime.now()
    start_date = end_date - timedelta(weeks=weeks)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT date, minutes 
        FROM gpu_activity 
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
    
    data = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    
    return data

def minutes_to_level(minutes):
    """Convert minutes to activity level (0-4)."""
    if minutes == 0:
        return 0
    elif minutes <= 60:
        return 1
    elif minutes <= 180:
        return 2
    elif minutes <= 360:
        return 3
    else:
        return 4

def generate_svg(data, theme="light"):
    """Generate GitHub-style contribution graph SVG."""
    # Calculate grid dimensions
    end_date = datetime.now()
    start_date = end_date - timedelta(days=364)
    # Align start_date to the previous Sunday
    start_date -= timedelta(days=(start_date.weekday() + 1) % 7)

    # Colors for different themes
    colors = {
        "light": {
            "bg": "#ffffff",
            "empty": "#ebedf0",
            "levels": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
            "text": "#57606a"
        },
        "dark": {
            "bg": "#0d1117",
            "empty": "#161b22",
            "levels": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
            "text": "#7d8590"
        }
    }

    theme_colors = colors.get(theme, colors["light"])

    # Generate day rectangles and collect month start positions
    rectangles = []
    month_labels = []
    current_date = start_date
    week = 0
    day_of_week = current_date.weekday()
    last_month = None
    month_positions = {}

    # Start from the beginning of the week
    if day_of_week != 6:  # If not Sunday
        week = -1

    # Count weeks for centering
    week_count = 0
    temp_date = start_date
    temp_week = week
    while temp_date <= end_date:
        if temp_date.weekday() == 6:
            temp_week += 1
        temp_date += timedelta(days=1)
    week_count = temp_week + 1

    plot_width = week_count * 13
    plot_x_offset = (760 - plot_width) // 2

    # Now generate the actual rectangles and month positions
    current_date = start_date
    week = 0
    day_of_week = current_date.weekday()
    if day_of_week != 6:
        week = -1

    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        minutes = data.get(date_str, 0)
        level = minutes_to_level(minutes)
        x = plot_x_offset + (week + 1) * 13
        y = ((current_date.weekday() + 1) % 7) * 13
        rect = f'<rect x="{x}" y="{y}" width="11" height="11" rx="2" fill="{theme_colors["levels"][level]}"><title>{date_str}: {minutes:.0f} minutes of GPU activity</title></rect>'
        rectangles.append(rect)
        # Month label logic: label the first week of each month
        if (current_date.day <= 7) and (current_date.month != last_month):
            month_positions[current_date.strftime('%b')] = x
            last_month = current_date.month
        current_date += timedelta(days=1)
        if current_date.weekday() == 6:  # Sunday
            week += 1
    # Month labels SVG
    month_labels_svg = ''
    for month, x in month_positions.items():
        month_labels_svg += f'<text x="{x+16}" y="10" fill="{theme_colors["text"]}" font-size="10" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif">{month}</text>'
    # Day-of-week labels SVG (Mon, Wed, Fri)
    day_labels = [("M  ", 1), ("W  ", 3), ("F  ", 5)]
    day_labels_svg = ''
    for label, idx in day_labels:
        y = idx * 13 + 11  # 11 centers the label in the square
        day_labels_svg += f'<text x="{plot_x_offset - 10}" y="{y}" fill="{theme_colors["text"]}" font-size="10" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif">{label}</text>'
    # Calculate stats
    total_days = len([m for m in data.values() if m > 0])
    total_hours = sum(data.values()) / 60
    # Current streak
    streak = 0
    check_date = end_date
    while check_date >= start_date:
        if data.get(check_date.strftime('%Y-%m-%d'), 0) > 0:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break
    # SVG template
    svg_width = 760
    svg_height = 130
    svg = f'''<svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">
    <rect width="{svg_width}" height="{svg_height}" fill="{theme_colors["bg"]}" rx="3"/>
    {month_labels_svg}
    <g transform="translate(0, 20)">
        {day_labels_svg}
        {''.join(rectangles)}
    </g>
    <text x="{plot_x_offset}" y="130" fill="{theme_colors["text"]}" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="11">
        {total_days} active days | {streak} day streak | {total_hours:.0f} total hours
    </text>
</svg>'''
    return svg

@app.get("/gpu-activity.svg")
async def gpu_activity_svg(theme: str = "light", weeks: int = 53):
    """Generate and return GPU activity SVG."""
    try:
        data = get_activity_data(weeks)
        svg = generate_svg(data, theme)
        
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "public, max-age=1800",  # 30 minute cache
                "X-Content-Type-Options": "nosniff",
            }
        )
    except Exception as e:
        logging.error(f"Error generating SVG: {e}")
        # Return empty SVG on error
        return Response(
            content='<svg width="722" height="130" xmlns="http://www.w3.org/2000/svg"></svg>',
            media_type="image/svg+xml"
        )

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

@app.get("/")
async def root():
    """Root endpoint with usage information."""
    return {
        "message": "GPU Activity SVG Generator",
        "endpoints": {
            "/gpu-activity.svg": "Generate GitHub-style contribution graph",
            "/health": "Health check",
            "/": "This help message"
        },
        "usage": {
            "svg": "/gpu-activity.svg?theme=light&weeks=53",
            "themes": ["light", "dark"],
            "weeks": "Number of weeks to display (default: 53)"
        }
    } 