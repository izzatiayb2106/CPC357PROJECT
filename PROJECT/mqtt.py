import json
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import paho.mqtt.client as mqtt
from datetime import datetime

# ================= CONFIGURATION =================
CRED_PATH = "firebase_key.json" 
MQTT_TOPIC = "iot"

# ================= SETUP =================
# 1. Connect to Firestore
cred = credentials.Certificate(CRED_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()

# 2. MQTT Callbacks
def on_connect(client, userdata, flags, rc):
    print("Connected to Mosquitto! Listening...")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        print(f"Received: {payload}")
        data = json.loads(payload)
        
        # Add Server Timestamp
        data["timestamp"] = datetime.now()

        # Save to Firestore (Collection: 'sensor_readings')
        db.collection("sensor_readings").add(data)
        print(" -> Saved to Firestore")
        
    except Exception as e:
        print(f"Error: {e}")

# ================= MAIN LOOP =================
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect("127.0.0.1", 1883, 60)
client.loop_forever()