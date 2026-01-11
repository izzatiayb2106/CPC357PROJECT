CPC357PROJECT
🚌 Smart Bus Stop Environmental, Comfort & Safety Automation System

📖 Project Summary

The Smart Bus Stop Environmental, Comfort & Safety Automation System is an IoT-based solution designed to improve the safety, comfort, and emergency responsiveness of semi-indoor public transportation shelters. By integrating environmental monitoring, human-centered automation, and emergency surveillance, this system transforms traditional bus stops into intelligent, secure, and energy-efficient urban infrastructure.

The system continuously monitors environmental conditions such as air quality, rain, lighting, and human presence. In addition, it introduces a panic-based emergency response mechanism using a physical push button and live camera feed. Based on real-time sensor data and emergency triggers, the system activates actuators including a servo-controlled window, smart fan, buzzer, adaptive LED lighting, and emergency camera recording.

This project supports SDG 11 (Sustainable Cities and Communities) by enhancing public safety, accessibility, and energy efficiency in urban public spaces.

🚀 Key Features

1️⃣ Environmental Monitoring & Safety (Outdoor + Indoor)
💨 Smart Weather Protection
Sensors: Outdoor Air Quality / Smoke Sensor & Rain Sensor
Action:
When hazardous air (haze/smoke) or rain is detected, the servo motor automatically closes the ventilation window to protect waiting passengers.

🚭 Anti-Smoking Alert
Sensor: Indoor Smoke Sensor
Action:
If cigarette smoke is detected inside the bus stop:
A buzzer is activated to alert users.
An alert is logged on the dashboard for monitoring and analysis.

2️⃣ Smart Comfort & Energy Efficiency (Indoor)
❄️ Adaptive Energy Control
Sensor: PIR Motion Sensor
Action:
The smart fan turns ON only when passengers are detected.
Automatically turns OFF when no motion is detected, reducing unnecessary power usage.

💡 Intelligent Lighting System
Sensor: LDR (Light Dependent Resistor)
Action:
LED strips automatically adjust brightness:
Dim during daylight hours to conserve energy
Brighten at night to improve visibility and safety

3️⃣ Emergency & Safety Enhancements 
🚨 Panic Button + Emergency Camera System
A push button is installed inside the bus stop to allow passengers to trigger an emergency response during critical situations such as:
Medical emergencies
Harassment or assault
Unsafe environmental conditions

When the Panic Button is Pressed:
🔘 Hardware Response
Panic button sends a signal to the ESP32
LED indicator flashes to acknowledge activation
Buzzer sounds briefly to indicate emergency mode

📷 Camera Response
Live CCTV feed remains active
System automatically:
Captures continuous frames and saves a 30–60 second emergency video recording. It records the moment before and after the panic event for evidence

☁️ Cloud & Dashboard Response
Emergency event is:
Logged in Firebase Firestore
Displayed instantly on the Streamlit dashboard

Emergency alerts include:
Timestamp
Event type (PANIC)
Camera recording status
Emergency videos are stored locally.

This enhancement significantly improves user safety, accountability, and real-time incident response, making the system suitable for smart city deployment.


▶️ How to Run the Project
Step 1: Start the Cloud Server (VM)
-Log in to Google Cloud Platform Console
-Start your Compute Engine VM instance
-Copy the External IP Address of the VM

Step 2: Run the MQTT Bridge (On VM)
-Open your SSH terminal
-Connect to the VM
-Activate your Python virtual environment
-Run the MQTT bridge script:
nano mqtt.py
python3 mqtt.py

⚠️ Keep this terminal open — it acts as the bridge between the ESP32 hardware and Firebase.

Step 3: Connect the Hardware (ESP32)
-Open Arduino IDE
-Open your main ESP32 sketch
-Paste the VM External IP into:
-const char* mqtt_server = "VM_EXTERNAL_IP";
-Connect ESP32 via USB and connect to wifi. 
-Upload the code and connect to MQTT

Step 4: Activate Python Virtual Environment
-source venv/bin/activate

Step 5: Install Required Libraries
-pip install streamlit firebase-admin pandas plotly opencv-python numpy python-multipart

Step 6: Run the Streamlit Dashboard
-python -m streamlit run dashboard.py


Python Dependencies:
These libraries are required to run the Streamlit dashboard, camera processing, Firebase integration, and MQTT communication.

Core Libraries
Python 3.8+
streamlit – Web-based dashboard UI
opencv-python (cv2) – Live camera feed and video recording
pandas – Sensor data processing and analytics
numpy – Numerical computations
threading – Background tasks (camera & data fetch)
collections (deque) – Efficient event and energy logs
datetime – Timestamp handling and time-based filtering
time – Timing control and delays
json – Data serialization for MQTT messages

Cloud & Database
firebase-admin – Firebase Firestore integration
google-cloud-firestore – Cloud database backend

Messaging / IoT Communication
paho-mqtt – MQTT client for ESP32 ↔ Cloud communication

Arduino / ESP32 Dependencies:
These libraries are required to compile and upload the firmware to the ESP32 microcontroller.

Core Libraries
Arduino IDE (ESP32 Board Package Installed)
WiFi.h – Wi-Fi connectivity for ESP32
PubSubClient.h – MQTT communication
ArduinoJson.h – JSON data formatting and parsing

Hardware Control
ESP32Servo.h – Servo motor control for automatic window operation

