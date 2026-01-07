# CPC357PROJECT

# Smart Bus Stop Environmental & Comfort Automation System 🚌✨

## 📖 Project Summary

The **Smart Bus Stop Environmental & Comfort Automation System** is an IoT-based solution designed to improve the safety, comfort, and sustainability of semi-indoor public transportation shelters. By integrating environmental monitoring with human-centered automation, this system transforms traditional bus stops into responsive, energy-efficient urban facilities.

The system continuously monitors conditions such as air quality, rain, and human presence. Based on real-time data, it triggers active actuators—including a servo-controlled window, smart fan, buzzer, and adaptive LED lighting—to create a safer and more comfortable waiting environment. This innovation supports **SDG 11 (Sustainable Cities and Communities)** by promoting energy-efficient infrastructure and public safety.

---

## 🚀 Key Features

### 1. Environmental Monitoring & Safety (Outdoor + Indoor)

- **💨 Smart Weather Protection:**
  - **Sensors:** Outdoor Air Quality/Smoke Sensor & Rain Sensor.
  - **Action:** If hazardous air (haze/smoke) or rain is detected, the **Servo Motor** automatically closes the ventilation window to protect passengers.
- **🚭 Anti-Smoking Alert:**
  - **Sensor:** Indoor Smoke Sensor.
  - **Action:** If cigarette smoke is detected inside, a **Buzzer** activates to alert the user and deter smoking.

### 2. Smart Comfort & Energy Efficiency (Indoor)

- **❄️ Adaptive Energy Control:**
  - **Sensor:** PIR Motion Sensor.
  - **Action:** The **Smart Fan** turns ON only when passengers are detected. It turns OFF automatically when the bus stop is empty to save energy.
- **💡 Intelligent Lighting:**
  - **Sensor:** LDR (Light Sensor).
  - **Action:** **LED Strips** automatically adjust brightness—dimming during the day to conserve power and brightening at night for safety and visibility.

---

How to Run the Project
Follow these steps in order to start the system.

Step 1: Start the Cloud Server (VM)
Log in to Google Cloud Platform Console.

Start your Compute Engine VM instance.

Copy the External IP Address of the VM.

Step 2: Run the MQTT Bridge (On VM)
Open your SSH terminal.

Connect to your VM.

Activate your Python virtual environment and run the bridge script:

# Command to run inside SSH
nano mqtt.py
python3 mqtt.py
Keep this terminal open. It acts as the bridge between the hardware and the database.

Step 3: Connect the Hardware (ESP32)
Open your Arduino IDE.

Open your main sketch file.

Paste the new VM External IP into the mqtt_server variable in your code.

Connect your ESP32 board via USB.

Upload the code and Connect to MQTT.

Step 4: Launch the Dashboard 

Navigate to your project folder.

Run the Streamlit dashboard:

python -m streamlit run dashboard.py



