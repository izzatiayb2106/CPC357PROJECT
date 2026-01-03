import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import pandas as pd
import time
from datetime import datetime, timedelta
import cv2
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
if 'ui_frame_skip' not in st.session_state:
    st.session_state.ui_frame_skip = 0

# ================= HELPER FUNCTIONS =================
def camera_capture_thread(camera_source, width, height, stop_flag, frame_container):
    """Background thread for continuous camera capture"""
    try:
        # Try DirectShow first (Windows) - best for Logitech
        cap = cv2.VideoCapture(camera_source, cv2.CAP_DSHOW)
        time.sleep(0.3)
        
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(camera_source)
            time.sleep(0.3)
        
        if cap.isOpened():
            # Optimal settings for C922 Pro
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency
            
            # Disable auto-adjust for consistent frame times
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
            
            # Warm up camera
            for _ in range(10):
                cap.read()
            
            print(f"✓ Camera initialized: {width}x{height} @ 30fps")
            
            frame_count = 0
            while not stop_flag.is_set():
                ret, frame = cap.read()
                if ret:
                    # Convert and store frame
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_container['frame'] = frame_rgb
                    frame_container['frame_id'] = frame_count
                    frame_count += 1
                    
                    if frame_count % 300 == 0:  # Log every 10 seconds
                        print(f"✓ Captured {frame_count} frames")
                    
                    # Precise timing for 30 FPS
                    time.sleep(0.033)
                else:
                    time.sleep(0.05)
            
            cap.release()
            print("✓ Camera stopped cleanly")
        else:
            print(f"✗ Failed to open camera at index {camera_source}")
    except Exception as e:
        print(f"✗ Camera thread error: {e}")

def start_camera_thread(camera_source, width, height):
    """Start the camera capture thread"""
    if not st.session_state.camera_thread_running:
        st.session_state.camera_thread_running = True
        st.session_state.camera_stop_flag.clear()
        
        # Create a container dict for thread-safe frame sharing
        if 'camera_frame_container' not in st.session_state:
            st.session_state.camera_frame_container = {'frame': None}
        
        thread = threading.Thread(
            target=camera_capture_thread,
            args=(camera_source, width, height, st.session_state.camera_stop_flag, st.session_state.camera_frame_container),
            daemon=True
        )
        thread.start()
        print(f"Starting camera thread for source {camera_source}")

def stop_camera_thread():
    """Stop the camera capture thread"""
    st.session_state.camera_thread_running = False
    st.session_state.camera_stop_flag.set()
    if 'camera_frame_container' in st.session_state:
        st.session_state.camera_frame_container['frame'] = None
    time.sleep(0.3)  # Give thread time to clean up
    print("Camera thread stop requested")

def reset_daily_counter():
    """Reset daily read counter at midnight"""
    today = datetime.now().date()
    if st.session_state.last_reset != today:
        st.session_state.daily_reads = 0
        st.session_state.last_reset = today

def should_fetch_data(interval_seconds=5):
    """Smart fetch - only fetch if enough time has passed"""
    if st.session_state.last_fetch_time is None:
        return True
    elapsed = (datetime.now() - st.session_state.last_fetch_time).total_seconds()
    return elapsed >= interval_seconds

def fetch_firestore_data(limit=50):
    """Fetch data from Firestore with read tracking"""
    reset_daily_counter()
    
    # Check if we're approaching daily limit
    if st.session_state.daily_reads >= 45000:  # Leave buffer
        st.warning("⚠️ Approaching daily Firestore read limit. Using cached data.")
        return st.session_state.cached_data
    
    try:
        docs = db.collection("sensor_readings")\
                 .order_by("timestamp", direction=firestore.Query.DESCENDING)\
                 .limit(limit).stream()
        
        data_list = [doc.to_dict() for doc in docs]
        st.session_state.cached_data = data_list
        st.session_state.last_fetch_time = datetime.now()
        st.session_state.daily_reads += limit
        st.session_state.fetch_counter += 1
        
        return data_list
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return st.session_state.cached_data

def calculate_energy_usage(motion_detected, duration_minutes=1):
    """Calculate energy usage based on motion detection"""
    active_power = 50  # Watts
    standby_power = 5  # Watts
    
    if motion_detected:
        energy = active_power * (duration_minutes / 60)  # Wh
    else:
        energy = standby_power * (duration_minutes / 60)  # Wh
    
    return energy

def filter_data_by_period(df, period):
    """Filter dataframe by time period"""
    if df.empty or 'timestamp' not in df.columns:
        return df
    
    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Make timezone-aware if needed
    now = pd.Timestamp.now(tz='UTC')
    if df['timestamp'].dt.tz is None:
        # If data is timezone-naive, make it UTC
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
    
    if period == "Day":
        start_time = now - timedelta(days=1)
    elif period == "Week":
        start_time = now - timedelta(weeks=1)
    elif period == "Month":
        start_time = now - timedelta(days=30)
    else:
        return df
    
    return df[df['timestamp'] >= start_time]

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
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .camera-container {
        position: sticky;
        top: 20px;
        border: 3px solid #667eea;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
    }
    .live-badge {
        position: absolute;
        top: 10px;
        left: 10px;
        background: #ef4444;
        color: white;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: bold;
        z-index: 100;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
</style>
""", unsafe_allow_html=True)

# ================= SIDEBAR =================
with st.sidebar:
    st.image("https://via.placeholder.com/150x50/667eea/ffffff?text=SmartBus", width='stretch')
    st.markdown("---")
    
    st.subheader("⚙️ Settings")
    
    refresh_interval = st.slider("Data Refresh Interval (seconds)", 3, 30, 5)
    camera_enabled = st.checkbox("Enable Live Camera", value=True)
    
    st.markdown("**🎥 Camera Settings (Logitech C922 Pro)**")
    camera_source = st.number_input("Camera Source", 0, 10, 0, help="Usually 0 for first USB camera")
    
    resolution_option = st.selectbox(
        "Resolution",
        ["720p (1280x720) - Recommended", "1080p (1920x1080)", "480p (640x480)"],
        index=0
    )
    
    # Parse resolution
    if "1080p" in resolution_option:
        cam_width, cam_height = 1920, 1080
    elif "720p" in resolution_option:
        cam_width, cam_height = 1280, 720
    else:
        cam_width, cam_height = 640, 480
    
    # Fixed UI refresh rate at 15 FPS for smooth performance
    ui_refresh_delay = 0.067  # ~15 FPS
    
    st.markdown("---")
    st.subheader("📊 Data Analysis")
    time_period = st.selectbox("Time Period", ["Day", "Week", "Month"])
    
    st.markdown("---")
    st.subheader("📈 System Stats")
    st.metric("Total Fetches", st.session_state.fetch_counter)
    st.metric("Daily Reads", f"{st.session_state.daily_reads:,} / 50,000")
    
    reads_percentage = (st.session_state.daily_reads / 50000) * 100
    st.progress(reads_percentage / 100)
    
    if reads_percentage > 90:
        st.error("⚠️ Critical: Near daily limit!")
    elif reads_percentage > 70:
        st.warning("⚠️ Warning: High usage")
    else:
        st.success("✓ Usage normal")

# ================= MAIN CONTENT =================
st.markdown('<h1 class="main-header">🚌 Smart Bus Stop Dashboard</h1>', unsafe_allow_html=True)

# Create layout containers
camera_col, metrics_col = st.columns([1.2, 1])

# Camera Feed Section
with camera_col:
    st.markdown("### 📹 Live CCTV Feed")
    camera_placeholder = st.empty()

# Metrics Section
with metrics_col:
    st.subheader("📊 Current Status")
    metrics_placeholder = st.empty()

# Charts Section
st.markdown("---")
chart_tabs = st.tabs(["📈 Live Trends", "⚡ Energy Monitor", "🌡️ Air Quality Analysis"])

with chart_tabs[0]:
    trends_placeholder = st.empty()

with chart_tabs[1]:
    energy_placeholder = st.empty()

with chart_tabs[2]:
    air_quality_placeholder = st.empty()

# Data Table Section
with st.expander("🗂️ Raw Sensor Data", expanded=False):
    data_table_placeholder = st.empty()

# ================= CAMERA MANAGEMENT =================
if camera_enabled:
    start_camera_thread(camera_source, cam_width, cam_height)
else:
    stop_camera_thread()

# ================= MAIN LOOP =================
loop_counter = 0

while True:
    loop_counter += 1
    
    # Update Camera Feed (every loop for smooth video)
    if camera_enabled:
        current_frame = st.session_state.camera_frame_container.get('frame') if 'camera_frame_container' in st.session_state else None
        
        if current_frame is not None:
            try:
                # Convert frame to bytes to avoid caching issues
                import io
                from PIL import Image
                
                pil_image = Image.fromarray(current_frame.astype('uint8'))
                img_bytes = io.BytesIO()
                pil_image.save(img_bytes, format='JPEG', quality=85)
                img_bytes.seek(0)
                
                camera_placeholder.image(
                    img_bytes,
                    channels="RGB",
                    width='stretch'
                )
            except Exception as e:
                print(f"Frame display error: {e}")
        else:
            # Show diagnostic info
            with camera_placeholder.container():
                st.info("📷 Initializing camera feed...")
                st.caption(f"Camera Source: {camera_source} | Resolution: {cam_width}x{cam_height}")
                
                if loop_counter > 30:
                    st.warning("""
                    ⚠️ Camera is taking longer than expected...
                    
                    **Check:**
                    - Camera is plugged into USB 3.0 port
                    - No other apps are using the camera
                    - Try a different Camera Source number
                    
                    Look at the terminal for error messages.
                    """)
    else:
        camera_placeholder.info("📷 Camera feed disabled. Enable in sidebar to start live feed.")
        stop_camera_thread()
    
    # Only fetch data at specified intervals
    if should_fetch_data(refresh_interval):
        data_list = fetch_firestore_data(limit=50)
    else:
        data_list = st.session_state.cached_data
    
    if data_list:
        df = pd.DataFrame(data_list)
        
        # Ensure timestamp is datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp', ascending=False)
        
        latest = df.iloc[0]
        
        # Update Metrics
        with metrics_placeholder.container():
            m1, m2 = st.columns(2)
            m3, m4 = st.columns(2)
            
            smoke_val = latest.get('smoke', 0)
            air_val = latest.get('air', 0)
            rain_val = latest.get('rain', False)
            window_val = latest.get('window', 'UNKNOWN')
            motion_val = latest.get('motion_detected', False)
            
            # Smoke metric with color coding
            smoke_color = "🟢" if smoke_val < 300 else "🟡" if smoke_val < 600 else "🔴"
            m1.metric("💨 Smoke Level", f"{smoke_val} {smoke_color}", 
                     delta=None, delta_color="off")
            
            # Air quality metric
            air_color = "🟢" if air_val < 100 else "🟡" if air_val < 200 else "🔴"
            m2.metric("🌫️ Air Quality", f"{air_val} {air_color}", 
                     delta=None, delta_color="off")
            
            # Rain status
            m3.metric("🌧️ Rain Detected", "YES ☔" if rain_val else "NO ☀️")
            
            # Window status
            m4.metric("🪟 Window Status", window_val)
            
            # Motion and energy
            st.markdown("---")
            e1, e2 = st.columns(2)
            motion_status = "🟢 ACTIVE" if motion_val else "⚪ IDLE"
            e1.metric("👤 Motion Sensor", motion_status)
            
            # Calculate energy
            energy_used = calculate_energy_usage(motion_val, duration_minutes=refresh_interval/60)
            st.session_state.motion_log.append({
                'timestamp': datetime.now(),
                'motion': motion_val,
                'energy': energy_used
            })
            e2.metric("⚡ Current Power", f"{50 if motion_val else 5} W")
        
        # Update Live Trends
        with trends_placeholder.container():
            if len(df) > 1:
                chart_df = df[['timestamp', 'smoke', 'air']].set_index('timestamp')
                st.line_chart(chart_df, height=300)
            else:
                st.info("Collecting data for trends...")
        
        # Update Energy Monitor
        with energy_placeholder.container():
            if len(st.session_state.motion_log) > 0:
                energy_df = pd.DataFrame(list(st.session_state.motion_log))
                energy_df['cumulative_energy'] = energy_df['energy'].cumsum()
                
                col1, col2 = st.columns(2)
                with col1:
                    total_energy = energy_df['cumulative_energy'].iloc[-1]
                    st.metric("⚡ Total Energy Used", f"{total_energy:.2f} Wh")
                    
                    active_time = energy_df['motion'].sum() * (refresh_interval / 60)
                    st.metric("⏱️ Active Time", f"{active_time:.1f} min")
                
                with col2:
                    avg_power = total_energy / (len(energy_df) * refresh_interval / 3600) if len(energy_df) > 0 else 0
                    st.metric("📊 Avg Power", f"{avg_power:.1f} W")
                    
                    savings = (50 - 5) * (len(energy_df) - energy_df['motion'].sum()) * (refresh_interval / 3600)
                    st.metric("💰 Energy Saved", f"{savings:.2f} Wh")
                
                # Energy chart
                st.line_chart(energy_df.set_index('timestamp')['cumulative_energy'], height=250)
            else:
                st.info("Collecting energy data...")
        
        # Update Air Quality Analysis
        with air_quality_placeholder.container():
            filtered_df = filter_data_by_period(df, time_period)
            
            if not filtered_df.empty and 'air' in filtered_df.columns:
                col1, col2, col3 = st.columns(3)
                
                avg_air = filtered_df['air'].mean()
                max_air = filtered_df['air'].max()
                min_air = filtered_df['air'].min()
                
                col1.metric(f"📊 Avg ({time_period})", f"{avg_air:.1f}")
                col2.metric("📈 Maximum", f"{max_air:.1f}")
                col3.metric("📉 Minimum", f"{min_air:.1f}")
                
                # Air quality chart
                air_chart_df = filtered_df[['timestamp', 'air']].set_index('timestamp')
                st.area_chart(air_chart_df, height=250)
                
                # Air quality assessment
                if avg_air < 100:
                    st.success(f"✅ Air quality is GOOD for the past {time_period.lower()}")
                elif avg_air < 200:
                    st.warning(f"⚠️ Air quality is MODERATE for the past {time_period.lower()}")
                else:
                    st.error(f"❌ Air quality is POOR for the past {time_period.lower()}")
            else:
                st.info(f"Collecting air quality data for {time_period.lower()}...")
        
        # Update Data Table
        with data_table_placeholder.container():
            display_df = df.head(20).copy()
            if 'timestamp' in display_df.columns:
                # Handle both timezone-aware and naive timestamps
                if display_df['timestamp'].dt.tz is not None:
                    display_df['timestamp'] = display_df['timestamp'].dt.tz_convert('UTC').dt.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            st.dataframe(display_df, width='stretch', height=300)
    
    else:
        st.warning("⚠️ No data available in Firestore yet...")
    
    # Smooth camera refresh with configurable FPS
    time.sleep(ui_refresh_delay)