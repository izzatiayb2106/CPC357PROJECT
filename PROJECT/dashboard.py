# type: ignore
import cv2
import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import pandas as pd
import time
from datetime import datetime, timedelta
import numpy as np
from collections import deque
import threading

# ================= PAGE CONFIG =================
st.set_page_config(
    page_title="Smart Bus Stop Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= FIREBASE SETUP =================
if not firebase_admin._apps:
    cred = credentials.Certificate("firebasekey.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

# ================= SESSION STATE INITIALIZATION =================
if 'last_fetch_time' not in st.session_state:
    st.session_state.last_fetch_time = None
if 'cached_data' not in st.session_state:
    st.session_state.cached_data = []
if 'fetch_counter' not in st.session_state:
    st.session_state.fetch_counter = 0
if 'daily_reads' not in st.session_state:
    st.session_state.daily_reads = 0
if 'last_reset' not in st.session_state:
    st.session_state.last_reset = datetime.now().date()
if 'motion_log' not in st.session_state:
    st.session_state.motion_log = deque(maxlen=1000)
if 'camera_cap' not in st.session_state:
    st.session_state.camera_cap = None
if 'camera_frame' not in st.session_state:
    st.session_state.camera_frame = None
if 'camera_thread_running' not in st.session_state:
    st.session_state.camera_thread_running = False
if 'camera_stop_flag' not in st.session_state:
    st.session_state.camera_stop_flag = threading.Event()
if 'camera_frame_container' not in st.session_state:
    st.session_state.camera_frame_container = {'frame': None}
# session states for emergency recording
if 'emergency_recording' not in st.session_state:
    st.session_state.emergency_recording = False
if 'emergency_record_start' not in st.session_state:
    st.session_state.emergency_record_start = None
if 'emergency_frames' not in st.session_state:
    st.session_state.emergency_frames = []
if 'saved_recordings' not in st.session_state:
    st.session_state.saved_recordings = []
if 'last_panic_state' not in st.session_state:
    st.session_state.last_panic_state = False
if 'panic_cooldown' not in st.session_state:
    st.session_state.panic_cooldown = None
# emergency recording thread state
if 'emergency_recording_thread_running' not in st.session_state:
    st.session_state.emergency_recording_thread_running = False
if 'emergency_stop_flag' not in st.session_state:
    st.session_state.emergency_stop_flag = threading.Event()
# missing alerts session states
if 'alerts_log' not in st.session_state:
    st.session_state.alerts_log = deque(maxlen=100)
if 'last_alert_state' not in st.session_state:
    st.session_state.last_alert_state = {}
if 'quota_exceeded' not in st.session_state:
    st.session_state.quota_exceeded = False
if 'quota_exceeded_time' not in st.session_state:
    st.session_state.quota_exceeded_time = None
if 'failed_fetch_count' not in st.session_state:
    st.session_state.failed_fetch_count = 0
if 'demo_mode' not in st.session_state:
    st.session_state.demo_mode = False
if 'last_data_update' not in st.session_state:
    st.session_state.last_data_update = datetime.now()
if 'last_analytics_update' not in st.session_state:
    st.session_state.last_analytics_update = datetime.now()
if 'component_refresh_log' not in st.session_state:
    st.session_state.component_refresh_log = {}
if 'fetch_thread_started' not in st.session_state:
    st.session_state.fetch_thread_started = False

# ================= SHARED STATE FOR BACKGROUND THREAD =================
if 'shared_data' not in st.session_state:
    st.session_state.shared_data = {
        'cached_data': [],
        'last_fetch_time': None,
        'daily_reads': 0,
        'fetch_counter': 0,
        'quota_exceeded': False,
        'quota_exceeded_time': None,
        'failed_fetch_count': 0,
        'last_data_update': None,
        'last_reset': datetime.now().date(),
    }
if 'data_lock' not in st.session_state:
    st.session_state.data_lock = threading.Lock()

# ================= COMPONENT REFRESH TIMING CONSTANTS =================
STATUS_INTERVAL = 5
TRENDS_INTERVAL = 10
ANALYTICS_INTERVAL = 60

# ================= HELPER FUNCTIONS =================
def should_update_component(component_name, interval_seconds):
    """Check if component needs update based on interval"""
    now = datetime.now()
    last_update = st.session_state.component_refresh_log.get(component_name, datetime.now() - timedelta(seconds=interval_seconds))
    elapsed = (now - last_update).total_seconds()
    if elapsed >= interval_seconds:
        st.session_state.component_refresh_log[component_name] = now
        return True
    return False

def get_time_until_refresh(component_name, interval_seconds):
    """Get seconds until next component refresh"""
    now = datetime.now()
    last_update = st.session_state.component_refresh_log.get(component_name, datetime.now() - timedelta(seconds=interval_seconds))
    elapsed = (now - last_update).total_seconds()
    return max(0, interval_seconds - elapsed)

def calculate_energy_usage(motion_detected, duration_minutes=1):
    """Calculate energy usage based on motion detection"""
    active_power = 50
    standby_power = 5
    if motion_detected:
        return active_power * (duration_minutes / 60)
    return standby_power * (duration_minutes / 60)

def filter_data_by_period(df, period):
    """Filter dataframe by time period"""
    if df.empty or 'timestamp' not in df.columns:
        return df
    if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    if df['timestamp'].dt.tz is not None:
        df['timestamp'] = df['timestamp'].dt.tz_convert('UTC').dt.tz_localize(None)
    now = datetime.now()
    if period == "Day":
        start_time = now - timedelta(days=1)
    elif period == "Week":
        start_time = now - timedelta(weeks=1)
    elif period == "Month":
        start_time = now - timedelta(days=30)
    else:
        return df
    return df[df['timestamp'] >= start_time]

def generate_mock_data(num_records=50):
    """Generate realistic mock sensor data for demo mode across multiple days"""
    import random
    mock_data = []
    base_time = datetime.now()
    for i in range(num_records):
        # Spread data across multiple days (each record ~2-6 hours apart)
        hours_offset = i * random.randint(2, 6)
        timestamp = base_time - timedelta(hours=hours_offset)
        
        # Simulate day/night cycle for LDR based on hour
        hour_of_day = timestamp.hour
        if 6 <= hour_of_day <= 18:  # Daytime
            ldr_value = random.randint(2000, 4000)
        else:  # Nighttime
            ldr_value = random.randint(100, 500)
        
        mock_record = {
            'timestamp': timestamp,
            'smoke': random.randint(500, 3500),
            'air': random.randint(800, 3000),
            'motion_detected': random.random() < 0.3,
            'rain': random.random() < 0.1,
            'ldr': ldr_value,
            'window': "CLOSED" if random.random() < 0.8 else "OPEN",
            'emergency': "false",
            'panic': "false",
        }
        mock_data.append(mock_record)
    return mock_data

def log_alert(event_type, trigger_source, details=""):
    """Log sensor and system alerts with deduplication"""
    alert_key = f"{event_type}_{trigger_source}"
    current_state = (event_type, trigger_source, details)
    if alert_key not in st.session_state.last_alert_state or \
       st.session_state.last_alert_state[alert_key] != current_state:
        alert = {
            'timestamp': datetime.now(),
            'event_type': event_type,
            'trigger_source': trigger_source,
            'details': details
        }
        st.session_state.alerts_log.append(alert)
        st.session_state.last_alert_state[alert_key] = current_state

def get_alert_icon(event_type):
    """Return appropriate icon for alert type"""
    icons = {
        'smoking': '🚬', 'fire_risk': '🔥', 'panic': '🚨',
        'emergency': '🆘', 'panic_button': '🔴',
        'camera_offline': '📷❌', 'camera_online': '📷✅',
        'recording_started': '⏺️', 'recording_saved': '💾'
    }
    return icons.get(event_type, '📍')

# ================= EMERGENCY RECORDING FUNCTIONS =================
def emergency_recording_thread(frame_container, frames_list, stop_flag, duration=30):
    """Background thread for continuous emergency recording"""
    start_time = time.time()
    frame_count = 0
    print(f"🔴 Emergency recording thread started - Recording for {duration} seconds")
    
    while not stop_flag.is_set() and (time.time() - start_time) < duration:
        current_frame = frame_container.get('frame')
        if current_frame is not None:
            frames_list.append(current_frame.copy())
            frame_count += 1
        time.sleep(0.1)  # Capture ~10 frames per second
    
    elapsed = time.time() - start_time
    print(f"⏹️ Emergency recording thread ended - Captured {frame_count} frames in {elapsed:.1f}s")

def start_emergency_recording():
    """Start recording frames for emergency"""
    if not st.session_state.emergency_recording:
        st.session_state.emergency_recording = True
        st.session_state.emergency_record_start = datetime.now()
        st.session_state.emergency_frames = []
        st.session_state.emergency_stop_flag.clear()
        
        log_alert('recording_started', 'Emergency Camera', 'Auto-recording started due to panic button (30 seconds)')
        print("🔴 Emergency recording started")
        
        # Start background recording thread if camera is available
        if st.session_state.camera_frame_container.get('frame') is not None:
            st.session_state.emergency_recording_thread_running = True
            record_thread = threading.Thread(
                target=emergency_recording_thread,
                args=(
                    st.session_state.camera_frame_container,
                    st.session_state.emergency_frames,
                    st.session_state.emergency_stop_flag,
                    30  # 30 seconds recording duration
                ),
                daemon=True
            )
            record_thread.start()
            
            # Start a timer thread to stop recording after 30 seconds
            def stop_after_duration():
                time.sleep(30)
                if st.session_state.emergency_recording:
                    stop_emergency_recording()
            
            timer_thread = threading.Thread(target=stop_after_duration, daemon=True)
            timer_thread.start()

def stop_emergency_recording():
    """Stop recording and save video"""
    if st.session_state.emergency_recording:
        st.session_state.emergency_recording = False
        st.session_state.emergency_recording_thread_running = False
        st.session_state.emergency_stop_flag.set()
        
        # Wait a moment for thread to finish
        time.sleep(0.2)
        
        frames = st.session_state.emergency_frames.copy()
        st.session_state.emergency_frames = []
        
        if len(frames) > 0:
            save_emergency_video(frames)
        else:
            print("⚠️ No frames captured for emergency recording")
            log_alert('recording_error', 'Emergency Camera', 'No frames captured - ensure camera is enabled')
        
        print(f"⏹️ Emergency recording stopped - {len(frames)} frames captured")

def save_emergency_video(frames):
    """Save recorded frames as video file"""
    import os
    
    # Create recordings directory
    recordings_dir = os.path.join(os.path.dirname(__file__), "emergency_recordings")
    os.makedirs(recordings_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"emergency_{timestamp}.avi"
    filepath = os.path.join(recordings_dir, filename)
    
    try:
        if len(frames) > 0:
            height, width = frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            out = cv2.VideoWriter(filepath, fourcc, 10.0, (width, height))
            
            for frame in frames:
                # Convert RGB back to BGR for saving
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(frame_bgr)
            
            out.release()
            
            recording_info = {
                'filename': filename,
                'filepath': filepath,
                'timestamp': datetime.now(),
                'duration': len(frames) / 10,  # Approximate duration in seconds
                'frame_count': len(frames),
                'type': 'PANIC_EMERGENCY'
            }
            st.session_state.saved_recordings.insert(0, recording_info)
            # Keep only last 20 recordings in memory
            st.session_state.saved_recordings = st.session_state.saved_recordings[:20]
            
            log_alert('recording_saved', 'Emergency Camera', f'Recording saved: {filename}')
            print(f"💾 Emergency video saved: {filepath}")
    except Exception as e:
        print(f"Error saving video: {e}")
        log_alert('recording_error', 'Emergency Camera', f'Failed to save: {str(e)}')

def check_and_handle_panic(latest_data):
    """Check for panic state and trigger appropriate actions"""
    
    panic_value = latest_data.get('panic', False)
    emergency_value = latest_data.get('emergency', False)
    
    # Handle string "true" or boolean True
    is_panic = (panic_value == True or panic_value == "true" or 
                emergency_value == True or emergency_value == "true")
    
    # Check cooldown (prevent repeated triggers within 60 seconds)
    cooldown_active = False
    if st.session_state.panic_cooldown:
        cooldown_elapsed = (datetime.now() - st.session_state.panic_cooldown).total_seconds()
        cooldown_active = cooldown_elapsed < 60
    
    # Detect new panic event (transition from False to True)
    if is_panic and not st.session_state.last_panic_state and not cooldown_active:
        # Log the panic alert
        log_alert('panic_button', 'PANIC BUTTON', '🚨 EMERGENCY! Panic button activated!')
        log_alert('emergency', 'Security System', 'Emergency mode activated - Window closed, alarm triggered')
        
        # Start emergency recording if camera is available
        if st.session_state.camera_frame_container.get('frame') is not None:
            start_emergency_recording()
        
        st.session_state.panic_cooldown = datetime.now()
        print("🚨 PANIC DETECTED - Emergency protocol initiated")
    
    # Update last panic state
    st.session_state.last_panic_state = is_panic
    
    return is_panic

def capture_emergency_frame():
    """Capture current frame for emergency recording (fallback if thread not running)"""
    if st.session_state.emergency_recording and not st.session_state.emergency_recording_thread_running:
        # Fallback: capture frame during page refresh if thread isn't running
        current_frame = st.session_state.camera_frame_container.get('frame')
        if current_frame is not None:
            st.session_state.emergency_frames.append(current_frame.copy())
    
    # Check if 30 seconds have passed and stop recording
    if st.session_state.emergency_recording and st.session_state.emergency_record_start:
        elapsed = (datetime.now() - st.session_state.emergency_record_start).total_seconds()
        if elapsed >= 30:
            stop_emergency_recording()

def display_emergency_recordings():
    """Display saved emergency recordings"""
    st.subheader("📹 Emergency Recordings")
    
    if st.session_state.emergency_recording:
        elapsed = 0
        if st.session_state.emergency_record_start:
            elapsed = (datetime.now() - st.session_state.emergency_record_start).total_seconds()
        remaining = max(0, 30 - elapsed)
        st.error(f"⏺️ **RECORDING IN PROGRESS** - {remaining:.0f}s remaining")
        st.progress(min(elapsed / 30, 1.0))
        st.caption(f"📊 Frames captured: {len(st.session_state.emergency_frames)}")
    
    if len(st.session_state.saved_recordings) > 0:
        for idx, recording in enumerate(st.session_state.saved_recordings[:5]):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.write(f"📁 **{recording['filename']}**")
                st.caption(f"Duration: {recording['duration']:.1f}s | Frames: {recording['frame_count']}")
            with col2:
                st.write(recording['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))
            with col3:
                if st.button(f"📂 Open Folder", key=f"open_{idx}"):
                    import subprocess
                    import os
                    folder = os.path.dirname(recording['filepath'])
                    if os.path.exists(folder):
                        subprocess.Popen(f'explorer "{folder}"')
    else:
        st.info("No emergency recordings yet")

def display_alerts_log():
    """Display scrollable alerts log with panic button alerts"""
    st.subheader("🚨 Alerts Log")
    
    # Show active emergency banner
    if st.session_state.last_panic_state:
        st.error("🆘 **ACTIVE EMERGENCY** - Panic button has been activated!")
    
    if len(st.session_state.alerts_log) > 0:
        alerts_df = pd.DataFrame(list(st.session_state.alerts_log))
        alerts_df['timestamp'] = pd.to_datetime(alerts_df['timestamp'])
        alerts_df = alerts_df.sort_values('timestamp', ascending=False)
        
        # Display alerts with styling based on type
        for idx, alert in alerts_df.head(10).iterrows():
            icon = get_alert_icon(alert['event_type'])
            time_str = alert['timestamp'].strftime('%H:%M:%S')
            
            # Highlight panic/emergency alerts
            if alert['event_type'] in ['panic_button', 'emergency', 'panic']:
                st.markdown(f"""
                <div style="background-color: #ffebee; border-left: 4px solid #f44336; padding: 10px; margin: 5px 0; border-radius: 4px;">
                    <strong>{icon} {time_str}</strong> | <strong style="color: #c62828;">{alert['trigger_source']}</strong><br>
                    <span style="color: #b71c1c;">{alert['details']}</span>
                </div>
                """, unsafe_allow_html=True)
            elif alert['event_type'] in ['recording_started', 'recording_saved']:
                st.markdown(f"""
                <div style="background-color: #e3f2fd; border-left: 4px solid #2196f3; padding: 10px; margin: 5px 0; border-radius: 4px;">
                    <strong>{icon} {time_str}</strong> | <strong>{alert['trigger_source']}</strong><br>
                    <span>{alert['details']}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                col1, col2, col3 = st.columns([0.5, 2, 2])
                col1.write(f"{icon} {time_str}")
                col2.write(f"**{alert['trigger_source']}**")
                col3.write(f"`{alert['event_type']}`")
        
        st.caption(f"Total Alerts: {len(st.session_state.alerts_log)}")
        
        # Clear alerts button
        if st.button("🗑️ Clear Alerts", key="clear_alerts"):
            st.session_state.alerts_log.clear()
            st.session_state.last_alert_state.clear()
            st.rerun()
    else:
        st.info("No alerts logged yet. All systems normal.")

def generate_historical_charts(df):
    """Generate historical analysis charts"""
    st.subheader("📊 Historical Charts")
    if len(df) < 3:
        st.info(f"⏳ Collecting historical data... ({len(df)} records)")
        return
    hist_tabs = st.tabs(["Air Quality", "Occupancy", "Lighting Usage", "Fan Duration"])
    with hist_tabs[0]:
        if 'timestamp' in df.columns and 'air' in df.columns:
            air_hist = df[['timestamp', 'air']].dropna().set_index('timestamp').sort_index()
            if not air_hist.empty:
                st.line_chart(air_hist, height=300)
                col1, col2, col3 = st.columns(3)
                col1.metric("Avg Air Quality", f"{df['air'].mean():.1f}")
                col2.metric("Max Reading", f"{df['air'].max():.1f}")
                col3.metric("Min Reading", f"{df['air'].min():.1f}")
                st.caption("📊 Lower values = Better air quality | Threshold: Good < 2000, Moderate < 3000, Poor ≥ 3000")
    with hist_tabs[1]:
        if 'timestamp' in df.columns and 'motion_detected' in df.columns:
            motion_hist = df[['timestamp', 'motion_detected']].copy()
            motion_hist['occupancy'] = motion_hist['motion_detected'].astype(int)
            motion_hist = motion_hist.set_index('timestamp').sort_index()
            if not motion_hist.empty:
                st.area_chart(motion_hist[['occupancy']], height=300)
    with hist_tabs[2]:
        if 'timestamp' in df.columns and 'ldr' in df.columns:
            light_df = df[['timestamp', 'ldr']].copy()
            light_df['hour'] = pd.to_datetime(light_df['timestamp']).dt.hour
            hourly_light = light_df.groupby('hour')['ldr'].mean()
            if not hourly_light.empty:
                st.bar_chart(hourly_light, height=300)
                st.caption("📊 Average light level (LDR) by hour of day - Higher = Brighter")
    with hist_tabs[3]:
        if 'timestamp' in df.columns and 'motion_detected' in df.columns:
            fan_df = df[['timestamp', 'motion_detected']].copy()
            fan_df['date'] = pd.to_datetime(fan_df['timestamp']).dt.date
            # Estimate fan duration: each motion detection = ~5 minutes of fan running
            fan_df['fan_minutes'] = fan_df['motion_detected'].astype(int) * 5
            daily_fan = fan_df.groupby('date')['fan_minutes'].sum()
            if not daily_fan.empty:
                st.bar_chart(daily_fan, height=300)
                col1, col2 = st.columns(2)
                col1.metric("Total Fan Time", f"{daily_fan.sum():.0f} min")
                col2.metric("Daily Average", f"{daily_fan.mean():.1f} min")
                st.caption("📊 Estimated fan running time per day (based on motion detections)")

# ================= CAMERA FUNCTIONS =================
def camera_capture_thread(camera_source, width, height, stop_flag, frame_container):
    """Background thread for continuous camera capture"""
    try:
        cap = cv2.VideoCapture(camera_source, cv2.CAP_DSHOW)
        time.sleep(0.3)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(camera_source)
            time.sleep(0.3)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, 10)
            for _ in range(10):
                cap.read()
            frame_count = 0
            while not stop_flag.is_set():
                ret, frame = cap.read()
                if ret:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_container['frame'] = frame_rgb
                    frame_container['frame_id'] = frame_count
                    frame_count += 1
                    time.sleep(0.033)
                else:
                    time.sleep(0.05)
            cap.release()
    except Exception as e:
        print(f"Camera error: {e}")

def start_camera_thread(camera_source, width, height):
    """Start the camera capture thread"""
    if not st.session_state.camera_thread_running:
        st.session_state.camera_thread_running = True
        st.session_state.camera_stop_flag.clear()
        thread = threading.Thread(
            target=camera_capture_thread,
            args=(camera_source, width, height, st.session_state.camera_stop_flag, st.session_state.camera_frame_container),
            daemon=True
        )
        thread.start()

def stop_camera_thread():
    """Stop the camera capture thread"""
    st.session_state.camera_thread_running = False
    st.session_state.camera_stop_flag.set()
    st.session_state.camera_frame_container['frame'] = None

# ================= THREAD-SAFE FETCH FUNCTIONS =================
def should_fetch_data_thread(shared, interval_seconds=5):
    """Thread-safe: Check if should fetch data"""
    if shared.get('quota_exceeded', False):
        quota_time = shared.get('quota_exceeded_time')
        if quota_time and (datetime.now() - quota_time).total_seconds() < 3600:
            return False
        shared['quota_exceeded'] = False
    last_fetch = shared.get('last_fetch_time')
    if last_fetch is None:
        return True
    return (datetime.now() - last_fetch).total_seconds() >= interval_seconds

def fetch_firestore_data_thread(shared, db_ref, limit=50):
    """Thread-safe: Fetch data from Firestore"""
    today = datetime.now().date()
    if shared.get('last_reset') != today:
        shared['daily_reads'] = 0
        shared['last_reset'] = today
    try:
        if shared.get('daily_reads', 0) >= 49000:
            shared['quota_exceeded'] = True
            shared['quota_exceeded_time'] = datetime.now()
            return shared.get('cached_data', [])
        print(f"📡 Fetching from Firestore (quota: {shared.get('daily_reads', 0)}/50000)...")
        docs = db_ref.collection("sensor_readings").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()
        data_list = [doc.to_dict() for doc in docs]
        if data_list:
            shared['cached_data'] = data_list
            shared['last_fetch_time'] = datetime.now()
            shared['daily_reads'] = shared.get('daily_reads', 0) + limit
            shared['fetch_counter'] = shared.get('fetch_counter', 0) + 1
            print(f"✓ Fetched {len(data_list)} records")
            return data_list
        return shared.get('cached_data', [])
    except Exception as e:
        print(f"Fetch error: {e}")
        if "quota" in str(e).lower():
            shared['quota_exceeded'] = True
            shared['quota_exceeded_time'] = datetime.now()
        return shared.get('cached_data', [])

# ================= SILENT DATA FETCH LOOP =================
def silent_data_fetch_loop(interval, db_ref, demo_mode_getter):
    """Background thread that fetches data every interval seconds"""
    def fetch_loop(shared, lock, db_ref):
        while True:
            try:
                # Check demo mode from shared state (thread-safe read)
                with lock:
                    is_demo = shared.get('demo_mode', False)
                
                if is_demo:
                    # Use mock data - NO Firebase fetch
                    import random
                    mock_data = []
                    base_time = datetime.now()
                    for i in range(50):
                        # Spread data across multiple days (each record ~2-6 hours apart)
                        hours_offset = i * random.randint(2, 6)
                        timestamp = base_time - timedelta(hours=hours_offset)
                        
                        # Simulate day/night cycle for LDR based on hour
                        hour_of_day = timestamp.hour
                        if 6 <= hour_of_day <= 18:  # Daytime
                            ldr_value = random.randint(2000, 4000)
                        else:  # Nighttime
                            ldr_value = random.randint(100, 500)
                        
                        mock_data.append({
                            'timestamp': timestamp,
                            'smoke': random.randint(500, 3500),
                            'air': random.randint(800, 3000),
                            'motion_detected': random.random() < 0.3,
                            'rain': random.random() < 0.1,
                            'ldr': ldr_value,
                            'window': "CLOSED" if random.random() < 0.8 else "OPEN",
                            'emergency': "false",
                            'panic': "false",
                        })
                    with lock:
                        shared['cached_data'] = mock_data
                        shared['fetch_counter'] = shared.get('fetch_counter', 0) + 1
                        shared['last_data_update'] = datetime.now()
                    print("🎮 Demo mode: Using mock data (no Firebase fetch)")
                else:
                    # Live mode - fetch from Firebase
                    with lock:
                        should_fetch = should_fetch_data_thread(shared, interval)
                    if should_fetch:
                        # Fetch outside lock to avoid blocking
                        data = fetch_firestore_data_thread(shared, db_ref, 50)
                        with lock:
                            shared['last_data_update'] = datetime.now()
            except Exception as e:
                print(f"Fetch loop error: {e}")
            time.sleep(interval)

    if not st.session_state.get('fetch_thread_started', False):
        shared = st.session_state.shared_data
        lock = st.session_state.data_lock
        fetch_thread = threading.Thread(target=fetch_loop, args=(shared, lock, db_ref), daemon=True)
        fetch_thread.start()
        st.session_state.fetch_thread_started = True
        print("✓ Background fetch thread started")

# Start the background fetch loop
silent_data_fetch_loop(STATUS_INTERVAL, db, lambda: st.session_state.demo_mode)

# ================= SYNC SHARED DATA TO SESSION STATE =================
with st.session_state.data_lock:
    st.session_state.cached_data = st.session_state.shared_data.get('cached_data', [])
    st.session_state.fetch_counter = st.session_state.shared_data.get('fetch_counter', 0)
    st.session_state.daily_reads = st.session_state.shared_data.get('daily_reads', 0)
    st.session_state.quota_exceeded = st.session_state.shared_data.get('quota_exceeded', False)
    st.session_state.quota_exceeded_time = st.session_state.shared_data.get('quota_exceeded_time')
    # Sync demo_mode to shared_data for the background thread
    st.session_state.shared_data['demo_mode'] = st.session_state.demo_mode

# ================= CUSTOM CSS =================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# ================= SIDEBAR =================
with st.sidebar:
    st.subheader("⚙️ Settings")
    st.markdown("**🎮 DEMO MODE**")
    demo_mode = st.checkbox("Enable Demo Mode (Mock Data)", value=st.session_state.demo_mode, 
                           help="When enabled, uses generated mock data instead of fetching from Firebase to preserve daily quota")
    if demo_mode != st.session_state.demo_mode:
        st.session_state.demo_mode = demo_mode
        # Immediately sync to shared data for background thread
        with st.session_state.data_lock:
            st.session_state.shared_data['demo_mode'] = demo_mode
        if demo_mode:
            st.toast("🎮 Demo mode enabled - Using mock data", icon="✅")
        else:
            st.toast("📡 Live mode enabled - Fetching from Firebase", icon="✅")
    st.markdown("---")
    camera_enabled = st.checkbox("Enable Live Camera", value=False)
    st.markdown("**🎥 Camera Settings**")
    camera_source = st.number_input("Camera Source", 0, 10, 0)
    resolution_option = st.selectbox("Resolution", ["720p (1280x720)", "1080p (1920x1080)", "480p (640x480)"], index=0)
    if "1080p" in resolution_option:
        cam_width, cam_height = 1920, 1080
    elif "720p" in resolution_option:
        cam_width, cam_height = 1280, 720
    else:
        cam_width, cam_height = 640, 480
    st.markdown("---")
    st.subheader("📊 Data Analysis")
    time_period = st.selectbox("Time Period", ["Day", "Week", "Month"])
    st.markdown("---")
    st.subheader("📈 System Stats")
    if st.session_state.demo_mode:
        st.info("🎮 **DEMO MODE ACTIVE**\n\nNo Firebase reads - using mock data")
    elif st.session_state.quota_exceeded:
        st.warning("🔴 **QUOTA EXCEEDED**")
    else:
        st.success("✓ **LIVE MODE**")
    st.metric("Total Fetches", st.session_state.fetch_counter)
    reads_percentage = (st.session_state.daily_reads / 50000) * 100
    st.metric("Daily Reads", f"{st.session_state.daily_reads:,} / 50,000")
    st.progress(min(reads_percentage / 100, 1.0))
    if st.session_state.demo_mode:
        st.caption("💡 Daily reads frozen in demo mode")

# ================= CAMERA MANAGEMENT =================
if camera_enabled:
    start_camera_thread(camera_source, cam_width, cam_height)
else:
    stop_camera_thread()

# ================= MAIN CONTENT =================
st.markdown('<h1 class="main-header">🚌 Smart Bus Stop Dashboard</h1>', unsafe_allow_html=True)

# Get data from session state (synced from background thread)
data_list = st.session_state.cached_data
df = pd.DataFrame(data_list) if data_list else pd.DataFrame()
if not df.empty and 'timestamp' in df.columns:
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp', ascending=False)
latest = df.iloc[0].to_dict() if not df.empty else {}

# ========== CHECK FOR PANIC BUTTON ==========
is_panic_active = check_and_handle_panic(latest)

# ========== CAPTURE EMERGENCY FRAMES ==========
capture_emergency_frame()

# ========== EMERGENCY BANNER ==========
if is_panic_active:
    st.markdown("""
    <div style="background-color: #f44336; color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px; animation: pulse 1s infinite;">
        <h2 style="margin: 0;">🚨 EMERGENCY ALERT 🚨</h2>
        <p style="margin: 10px 0 0 0; font-size: 18px;">Panic button has been activated! Emergency recording in progress.</p>
    </div>
    <style>
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
    </style>
    """, unsafe_allow_html=True)

# ========== CURRENT STATUS ==========
st.markdown("### 📊 Live Sensor Status")
col1, col2, col3, col4 = st.columns(4)
rain_val = latest.get('rain', False)
smoke_val = latest.get('smoke', 0)
air_val = latest.get('air', 0)
ldr_val = latest.get('ldr', 0)
smoke_color = "🟢" if smoke_val < 2000 else "🟡" if smoke_val < 3000 else "🔴"
air_color = "🟢" if air_val < 2000 else "🟡" if air_val < 3000 else "🔴"
ldr_color = "🌑" if ldr_val < 500 else "🌘" if ldr_val < 1500 else "🌗" if ldr_val < 2500 else "🌕"

col1.metric("🌧️ Rain Detected", "YES ☔" if rain_val else "NO ☀️")
col2.metric("💨 Smoke Sensor", f"{smoke_val} {smoke_color}")
col3.metric("🌫️ Air Quality", f"{air_val} {air_color}")
col4.metric("💡 LDR Sensor", f"{ldr_val} {ldr_color}")

# Update energy log
motion_val = latest.get('motion_detected', False)
energy_used = calculate_energy_usage(motion_val, duration_minutes=STATUS_INTERVAL/60)
st.session_state.motion_log.append({'timestamp': datetime.now(), 'motion': motion_val, 'energy': energy_used})

st.markdown("---")

# ========== ALERTS LOG ==========
display_alerts_log()

# ========== EMERGENCY RECORDINGS ==========
display_emergency_recordings()

st.markdown("---")

# ========== CAMERA FEED ==========
st.markdown("### 📹 Live CCTV Feed")
current_frame = st.session_state.camera_frame_container.get('frame')
if current_frame is not None:
    from PIL import Image
    import io
    pil_image = Image.fromarray(current_frame.astype('uint8'))
    img_bytes = io.BytesIO()
    pil_image.save(img_bytes, format='JPEG', quality=85)
    img_bytes.seek(0)
    # Use columns to constrain width - camera in center column
    cam_col1, cam_col2, cam_col3 = st.columns([1, 2, 1])
    with cam_col2:
        st.image(img_bytes, channels="RGB", width=680)
else:
    cam_col1, cam_col2, cam_col3 = st.columns([1, 2, 1])
    with cam_col2:
        st.info("📷 Camera not available or disabled")

st.markdown("---")

# ========== LIVE TRENDS ==========
st.markdown("### 📈 Live Trends")
if not df.empty and 'smoke' in df.columns and 'air' in df.columns:
    chart_df = df[['timestamp', 'smoke', 'air']].set_index('timestamp')
    st.line_chart(chart_df, height=300)
else:
    st.info("Collecting data for trends...")

# ========== ENERGY MONITOR ==========
st.markdown("### ⚡ Energy Monitor")
if len(st.session_state.motion_log) > 0:
    energy_df = pd.DataFrame(list(st.session_state.motion_log))
    energy_df['cumulative_energy'] = energy_df['energy'].cumsum()
    col1, col2 = st.columns(2)
    col1.metric("⚡ Total Energy Used", f"{energy_df['cumulative_energy'].iloc[-1]:.2f} Wh")
    col1.metric("⏱️ Active Time", f"{energy_df['motion'].sum() * (STATUS_INTERVAL / 60):.1f} min")
    avg_power = energy_df['cumulative_energy'].iloc[-1] / (len(energy_df) * STATUS_INTERVAL / 3600) if len(energy_df) > 0 else 0
    savings = (50 - 5) * (len(energy_df) - energy_df['motion'].sum()) * (STATUS_INTERVAL / 3600)
    col2.metric("📊 Avg Power", f"{avg_power:.1f} W")
    col2.metric("💰 Energy Saved", f"{savings:.2f} Wh")
    st.line_chart(energy_df.set_index('timestamp')['cumulative_energy'], height=250)
else:
    st.info("Collecting energy data...")

# ========== AIR QUALITY ANALYSIS ==========
st.markdown("### 🌡️ Air Quality Analysis")
if not df.empty and 'air' in df.columns:
    filtered_df = filter_data_by_period(df.copy(), time_period)
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        avg_air = filtered_df['air'].mean()
        col1.metric(f"📊 Avg ({time_period})", f"{avg_air:.1f}")
        col2.metric("📈 Maximum", f"{filtered_df['air'].max():.1f}")
        col3.metric("📉 Minimum", f"{filtered_df['air'].min():.1f}")
        air_chart_df = filtered_df[['timestamp', 'air']].set_index('timestamp')
        st.area_chart(air_chart_df, height=250)
        if avg_air < 100:
            st.success(f"✅ Air quality is GOOD for the past {time_period.lower()}")
        elif avg_air < 200:
            st.warning(f"⚠️ Air quality is MODERATE for the past {time_period.lower()}")
        else:
            st.error(f"❌ Air quality is POOR for the past {time_period.lower()}")
else:
    st.info("No air quality data available")

st.markdown("---")

# ========== HISTORICAL CHARTS ==========
if not df.empty:
    generate_historical_charts(df)

# ========== RAW DATA TABLE ==========
with st.expander("🗂️ Raw Sensor Data", expanded=False):
    if not df.empty:
        display_df = df.head(20).copy()
        if 'timestamp' in display_df.columns:
            display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        st.dataframe(display_df, width='stretch', height=300)
    else:
        st.info("No data available")

# ================= AUTO-REFRESH USING STREAMLIT-AUTOREFRESH =================
# Install: pip install streamlit-autorefresh
try:
    from streamlit_autorefresh import st_autorefresh
    # Refresh every 5 seconds (5000 ms) - this only refreshes the data display, not the entire page
    st_autorefresh(interval=5000, limit=None, key="data_refresh")
except ImportError:
    st.warning("Install streamlit-autorefresh for auto-refresh: `pip install streamlit-autorefresh`")
    if st.button("🔄 Refresh Data"):
        st.rerun()