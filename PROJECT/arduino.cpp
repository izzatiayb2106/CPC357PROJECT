#include <ESP32Servo.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h> 

// =========================================================
// 1. WIFI & MQTT CONFIGURATION
// =========================================================
const char* WIFI_SSID = "izzatiayb";       
const char* WIFI_PASSWORD = "izzati1234"; 

const char* MQTT_SERVER = "34.69.160.62"; // GCP VM IP
const char* MQTT_TOPIC = "iot";            // Topic to publish 
const int MQTT_PORT = 1883; 

WiFiClient espClient;
PubSubClient client(espClient);

// =========================================================
// 2. PIN DEFINITIONS
// =========================================================
const int ldrPin = A4;        // Analog Input (A4)
const int pirPin = 5;         // Digital Input (Left Port)

// --- BREADBOARD SENSORS ---
const int mq2Pin = A1;        // MQ2 Indoor Smoke (A1)
const int mq135Pin = A2;      // MQ135 Outdoor Air (A2)
const int rainPin = 10;       // Rain Sensor (Digital D10)

// --- ACTUATORS ---
const int fanRelayPin = 14;   // Relay Ch1 (Fan) - D14
const int ledRelayPin = 47;   // Relay Ch2 (LED) - D47
const int servoPin = 21;      // Servo Motor - D21
const int buzzerPin = 12;     // Built-in Buzzer - D12

// =========================================================
// 3. SETTINGS & VARIABLES
// =========================================================
// SENSOR THRESHOLDS
const int smokeThreshold = 4000;      
const int airQualityThreshold = 4000; 
const int lightThreshold = 1500;      

const bool TEST_MODE = false; 

Servo windowServo; 
volatile bool motionDetected = false; 
bool isSystemActive = false;          
unsigned long lastMotionTime = 0;     
const int activeDuration = 2000;      

bool isWindowClosed = false;          
int windowOpenAngle = 0;    
int windowClosedAngle = 100; 

// MQTT Timer
unsigned long lastMsgTime = 0;
const long interval = 10000; // Send data every 10 seconds

// =========================================================
// 4. HELPER FUNCTIONS
// =========================================================

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void reconnect() {
  // Loop until we're reconnected
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Attempt to connect
    if (client.connect("ESP32_IoT_Client")) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void playTone(int pin, int frequency, int duration) {
  long delayAmount = 1000000 / frequency / 2;
  long loops = frequency * duration / 1000;
  for (long i = 0; i < loops; i++) {
    digitalWrite(pin, HIGH);
    delayMicroseconds(delayAmount);
    digitalWrite(pin, LOW);
    delayMicroseconds(delayAmount);
  }
}

void IRAM_ATTR motionDetect() {
  motionDetected = true; 
}

// =========================================================
// 5. SETUP
// =========================================================
void setup() {
  Serial.begin(9600);
  
  // A. PIN MODES
  pinMode(pirPin, INPUT);
  pinMode(rainPin, INPUT);
  pinMode(mq2Pin, INPUT);
  pinMode(mq135Pin, INPUT);
  pinMode(ldrPin, INPUT);
  
  pinMode(fanRelayPin, OUTPUT);
  pinMode(ledRelayPin, OUTPUT);
  pinMode(buzzerPin, OUTPUT);

  // B. ACTUATOR DEFAULTS
  digitalWrite(fanRelayPin, HIGH); 
  digitalWrite(ledRelayPin, HIGH); 

  // C. SERVO SETUP
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
  windowServo.setPeriodHertz(50);    
  windowServo.attach(servoPin, 500, 2400); 
  windowServo.write(windowOpenAngle); 

  attachInterrupt(digitalPinToInterrupt(pirPin), motionDetect, RISING);

  // D. CONNECT
  setup_wifi();
  client.setServer(MQTT_SERVER, MQTT_PORT);
}

// =========================================================
// 6. MAIN LOOP
// =========================================================
void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // 1. READ SENSORS (With stability delay)
  analogRead(mq2Pin); delay(5);
  int smokeValue = analogRead(mq2Pin); 

  analogRead(mq135Pin); delay(5);
  int airValue = analogRead(mq135Pin);

  int lightLevel = analogRead(ldrPin);
  bool rainDetected = (digitalRead(rainPin) == LOW);

  // =============================================
  // 2. LOCAL AUTOMATION 
  // =============================================

  // --- Smoke Alarm ---
  bool smokeAlarm = (TEST_MODE) ? (smokeValue < smokeThreshold) : (smokeValue > smokeThreshold);
  if (smokeAlarm) {
    Serial.print("HAZARD: Smoke Detected! Val: ");
    Serial.println(smokeValue);
    playTone(buzzerPin, 1000, 100); 
  }

  // --- Window Control ---
  bool badAir = (TEST_MODE) ? (airValue < airQualityThreshold) : (airValue > airQualityThreshold);
  
  if (rainDetected || badAir) {
    if (!isWindowClosed) {
      if (rainDetected) Serial.println("WEATHER: Rain -> Closing Window");
      if (badAir) Serial.println("WEATHER: Bad Air -> Closing Window");
      windowServo.write(windowClosedAngle); 
      isWindowClosed = true;
    }
  } else {
    if (isWindowClosed) {
      Serial.println("WEATHER: Clear -> Opening Window");
      windowServo.write(windowOpenAngle);
      isWindowClosed = false;
    }
  }

  // --- Smart Lighting ---
  bool isDark = (lightLevel > lightThreshold);

  if (motionDetected) {
    if (!isSystemActive) {
      digitalWrite(fanRelayPin, LOW); // Fan ON
      Serial.print("MOTION: Fan ON");
      
      if (isDark) {
        digitalWrite(ledRelayPin, LOW); // LED ON
        Serial.println(" & Room Dark -> LED BRIGHT");
      } else {
        digitalWrite(ledRelayPin, HIGH); // LED OFF
        Serial.println(" & Room Bright -> LED DIM");
      }
      isSystemActive = true;
    }
    lastMotionTime = millis();
    motionDetected = false;
  }

  // Timer to Turn OFF
  if (isSystemActive && (millis() - lastMotionTime > activeDuration)) {
    digitalWrite(fanRelayPin, HIGH); // OFF
    digitalWrite(ledRelayPin, HIGH); // OFF
    isSystemActive = false;
    Serial.println("MOTION END: Fan OFF & LED Dim");
  }

  // =============================================
  // 3. MQTT PUBLISHING
  // =============================================
  unsigned long now = millis();
  if (now - lastMsgTime > interval) {
    lastMsgTime = now;

    // Create JSON Payload
    StaticJsonDocument<256> doc;
    doc["smoke"] = smokeValue;
    doc["air"] = airValue;
    doc["light"] = lightLevel;
    doc["rain"] = rainDetected; // true/false
    doc["motion"] = isSystemActive; // true/false
    
    // Add actuator status for dashboard feedback
    doc["window"] = isWindowClosed ? "CLOSED" : "OPEN";

    char jsonBuffer[512];
    serializeJson(doc, jsonBuffer);

    // Publish to GCP
    client.publish(MQTT_TOPIC, jsonBuffer);
    
    // Print to Serial for debugging
    Serial.print("MQTT SENT: ");
    Serial.println(jsonBuffer);
  }
  
  delay(10); // Small stability delay for loop
}