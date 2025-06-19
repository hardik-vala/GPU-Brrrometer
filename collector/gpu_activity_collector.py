#!/usr/bin/env python3

import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
import statistics
import argparse
import time
from pynvml import *

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

DB_PATH = "/var/lib/gpu-brrrometer/activity.db"
UTILIZATION_THRESHOLD = 1.0
SAMPLING_INTERVAL = 5  # Sample every 5 seconds

def init_database():
    """Create database and tables if they don't exist."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gpu_activity (
            date TEXT PRIMARY KEY,
            minutes REAL DEFAULT 0,
            peak_utilization INTEGER DEFAULT 0,
            avg_utilization REAL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON gpu_activity(date DESC)")
    conn.commit()
    conn.close()

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='GPU Activity Collector')
    parser.add_argument('--dry-run', action='store_true',
                      help='Show metrics without updating database')
    parser.add_argument('--show-db', action='store_true',
                      help='Display database contents and exit')
    return parser.parse_args()

def get_gpu_utilization():
    """Get current GPU utilization."""
    try:
        # Initialize NVML
        nvmlInit()
        
        # Get handle to the first GPU
        handle = nvmlDeviceGetHandleByIndex(0)
        
        # Get utilization info
        utilization = nvmlDeviceGetUtilizationRates(handle)
        gpu_util = utilization.gpu
        
        # Shutdown NVML
        nvmlShutdown()
        
        return gpu_util
        
    except NVMLError as e:
        logging.error(f"NVML error: {e}")
        return 0
    except Exception as e:
        logging.error(f"Error getting GPU utilization: {e}")
        return 0

def update_database(minutes, peak, avg):
    """Update today's activity in database."""
    today = datetime.now().strftime('%Y-%m-%d')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get existing minutes for today
    cursor.execute("SELECT minutes, peak_utilization, avg_utilization FROM gpu_activity WHERE date = ?", (today,))
    row = cursor.fetchone()
    
    if row:
        total_minutes = row[0] + minutes
        max_peak = max(row[1], peak)
        # Calculate weighted average of existing and new average utilization
        if total_minutes > 0:
            weighted_avg = ((row[0] * row[2]) + (minutes * avg)) / total_minutes
        else:
            weighted_avg = avg
            
        cursor.execute("""
            UPDATE gpu_activity 
            SET minutes = ?, peak_utilization = ?, avg_utilization = ?, last_updated = CURRENT_TIMESTAMP
            WHERE date = ?
        """, (total_minutes, max_peak, round(weighted_avg, 1), today))
    else:
        cursor.execute("""
            INSERT INTO gpu_activity (date, minutes, peak_utilization, avg_utilization)
            VALUES (?, ?, ?, ?)
        """, (today, minutes, peak, avg))
    
    conn.commit()
    conn.close()
    
    logging.info(f"Updated {today}: +{minutes:.1f} minutes (total: {total_minutes if row else minutes:.1f})")

def cleanup_old_data():
    """Remove entries older than 365 days."""
    cutoff_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gpu_activity WHERE date < ?", (cutoff_date,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    if deleted > 0:
        logging.info(f"Cleaned up {deleted} old entries")

def show_database_contents():
    """Display the contents of the database in a readable format."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get all records ordered by date
        cursor.execute("""
            SELECT date, minutes, peak_utilization, avg_utilization, last_updated 
            FROM gpu_activity 
            ORDER BY date DESC
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("Database is empty")
            return
            
        # Print header
        print("\nGPU Activity Database Contents:")
        print("=" * 80)
        print(f"{'Date':<12} {'Active Minutes':<15} {'Peak %':<10} {'Avg %':<10} {'Last Updated':<20}")
        print("-" * 80)
        
        # Print each row
        for row in rows:
            date, minutes, peak, avg, updated = row
            print(f"{date:<12} {minutes:<15.1f} {peak:<10} {avg:<10.1f} {updated}")
            
        print("=" * 80)
        print(f"Total records: {len(rows)}")
        
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
    finally:
        conn.close()

def run_collector():
    """Main collection loop."""
    current_date = datetime.now().strftime('%Y-%m-%d')
    utilization_values = []
    last_update = datetime.now()
    
    while True:
        try:
            # Get current utilization
            utilization = get_gpu_utilization()
            utilization_values.append(utilization)
            
            # Check if we need to update the database (every minute)
            now = datetime.now()
            if (now - last_update).total_seconds() >= 60:
                # Calculate metrics for the last minute
                active_samples = [v for v in utilization_values if v > UTILIZATION_THRESHOLD]
                
                if active_samples:
                    active_minutes = len(active_samples) * SAMPLING_INTERVAL / 60
                    peak_utilization = max(active_samples)
                    avg_utilization = statistics.mean(active_samples)
                    
                    update_database(active_minutes, int(peak_utilization), round(avg_utilization, 1))
                
                # Reset for next minute
                utilization_values = []
                last_update = now
                
                # Check if date changed
                if now.strftime('%Y-%m-%d') != current_date:
                    current_date = now.strftime('%Y-%m-%d')
                    cleanup_old_data()
            
            time.sleep(SAMPLING_INTERVAL)
            
        except Exception as e:
            logging.error(f"Error in collection loop: {e}")
            time.sleep(SAMPLING_INTERVAL)  # Still sleep to prevent tight loop on error

def main():
    """Main execution function."""
    args = parse_args()
    
    try:
        if args.show_db:
            show_database_contents()
            return
            
        if args.dry_run:
            logging.info("Dry run - collecting samples for 1 minute...")
            utilization_values = []
            start_time = datetime.now()
            
            while (datetime.now() - start_time).total_seconds() < 60:
                utilization = get_gpu_utilization()
                utilization_values.append(utilization)
                time.sleep(SAMPLING_INTERVAL)

            active_samples = [v for v in utilization_values if v > UTILIZATION_THRESHOLD]
            if active_samples:
                active_minutes = len(active_samples) * SAMPLING_INTERVAL / 60
                peak_utilization = max(active_samples)
                avg_utilization = statistics.mean(active_samples)
                
                logging.info(f"Sample metrics:")
                logging.info(f"Active minutes: {active_minutes:.1f}")
                logging.info(f"Peak utilization: {peak_utilization}%")
                logging.info(f"Average utilization: {avg_utilization:.1f}%")
            else:
                logging.info("No GPU activity detected (all samples were 0%)")
            return
        
        logging.info("Initializing database...")
        init_database()
        
        # Start the collector
        logging.info("GPU Activity Collector started")
        run_collector()
        
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()